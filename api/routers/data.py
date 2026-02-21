# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/routers/data.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import os
import json
import math
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import config

try:
    from sqlalchemy import func, or_, select
    from sqlalchemy.exc import SQLAlchemyError
    from database.db_session import get_session
    from database.models import XhsCreator, XhsNote, XhsNoteComment
    SQLALCHEMY_AVAILABLE = True
except ModuleNotFoundError:
    func = or_ = select = None
    SQLAlchemyError = Exception
    get_session = None
    XhsCreator = XhsNote = XhsNoteComment = None
    SQLALCHEMY_AVAILABLE = False

router = APIRouter(prefix="/data", tags=["data"])

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"

DB_DISABLED_OPTIONS = {"json", "csv", "excel"}


def get_file_info(file_path: Path) -> dict:
    """Get file information"""
    stat = file_path.stat()
    record_count = None

    # Try to get record count
    try:
        if file_path.suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    record_count = len(data)
        elif file_path.suffix == ".csv":
            with open(file_path, "r", encoding="utf-8") as f:
                record_count = sum(1 for _ in f) - 1  # Subtract header row
    except Exception:
        pass

    return {
        "name": file_path.name,
        "path": str(file_path.relative_to(DATA_DIR)),
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "record_count": record_count,
        "type": file_path.suffix[1:] if file_path.suffix else "unknown"
    }


def _ensure_db_available():
    if not SQLALCHEMY_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="SQLAlchemy is not installed in current environment, cannot query XHS dashboard data.",
        )

    if config.SAVE_DATA_OPTION in DB_DISABLED_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Current SAVE_DATA_OPTION is '{config.SAVE_DATA_OPTION}', "
                "please switch to sqlite/db/postgres to query XHS dashboard data."
            ),
        )


def _normalize_page(page: int, page_size: int, max_page_size: int = 100) -> tuple[int, int, int]:
    safe_page = max(page, 1)
    safe_page_size = max(min(page_size, max_page_size), 1)
    offset = (safe_page - 1) * safe_page_size
    return safe_page, safe_page_size, offset


def _parse_count(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().replace(",", "")
    if not text:
        return 0

    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 100000000
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except ValueError:
        digits = re.findall(r"\d+", text)
        return int("".join(digits)) if digits else 0


def _creator_to_dict(item: XhsCreator) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "nickname": item.nickname,
        "avatar": item.avatar,
        "ip_location": item.ip_location,
        "desc": item.desc,
        "gender": item.gender,
        "follows": item.follows,
        "fans": item.fans,
        "interaction": item.interaction,
        "tag_list": item.tag_list,
        "add_ts": item.add_ts,
        "last_modify_ts": item.last_modify_ts,
    }


def _note_to_dict(item: XhsNote) -> dict:
    comment_count_num = _parse_count(item.comment_count)
    return {
        "id": item.id,
        "note_id": item.note_id,
        "user_id": item.user_id,
        "nickname": item.nickname,
        "avatar": item.avatar,
        "title": item.title,
        "desc": item.desc,
        "type": item.type,
        "liked_count": item.liked_count,
        "collected_count": item.collected_count,
        "comment_count": item.comment_count,
        "comment_count_num": comment_count_num,
        "share_count": item.share_count,
        "note_url": item.note_url,
        "ip_location": item.ip_location,
        "source_keyword": item.source_keyword,
        "tag_list": item.tag_list,
        "time": item.time,
        "last_update_time": item.last_update_time,
        "add_ts": item.add_ts,
        "last_modify_ts": item.last_modify_ts,
        "has_comments": comment_count_num > 0,
    }


def _comment_to_dict(item: XhsNoteComment) -> dict:
    return {
        "id": item.id,
        "comment_id": item.comment_id,
        "parent_comment_id": item.parent_comment_id,
        "note_id": item.note_id,
        "user_id": item.user_id,
        "nickname": item.nickname,
        "avatar": item.avatar,
        "ip_location": item.ip_location,
        "content": item.content,
        "sub_comment_count": item.sub_comment_count or 0,
        "like_count": item.like_count,
        "create_time": item.create_time,
        "add_ts": item.add_ts,
        "last_modify_ts": item.last_modify_ts,
        "sub_comments": [],
    }


def _build_comment_tree(comments: list[dict]) -> tuple[list[dict], int]:
    comment_map = {item["comment_id"]: item for item in comments if item.get("comment_id")}
    roots: list[dict] = []
    child_count = 0

    for item in comments:
        parent_comment_id = (item.get("parent_comment_id") or "").strip()
        comment_id = item.get("comment_id")
        if parent_comment_id and parent_comment_id != comment_id and parent_comment_id in comment_map:
            comment_map[parent_comment_id]["sub_comments"].append(item)
            child_count += 1
        else:
            roots.append(item)

    return roots, child_count


@router.get("/files")
async def list_data_files(platform: Optional[str] = None, file_type: Optional[str] = None):
    """Get data file list"""
    if not DATA_DIR.exists():
        return {"files": []}

    files = []
    supported_extensions = {".json", ".csv", ".xlsx", ".xls"}

    for root, dirs, filenames in os.walk(DATA_DIR):
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            if file_path.suffix.lower() not in supported_extensions:
                continue

            # Platform filter
            if platform:
                rel_path = str(file_path.relative_to(DATA_DIR))
                if platform.lower() not in rel_path.lower():
                    continue

            # Type filter
            if file_type and file_path.suffix[1:].lower() != file_type.lower():
                continue

            try:
                files.append(get_file_info(file_path))
            except Exception:
                continue

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x["modified_at"], reverse=True)

    return {"files": files}


@router.get("/files/{file_path:path}")
async def get_file_content(file_path: str, preview: bool = True, limit: int = 100):
    """Get file content or preview"""
    full_path = DATA_DIR / file_path

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    # Security check: ensure within DATA_DIR
    try:
        full_path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if preview:
        # Return preview data
        try:
            if full_path.suffix == ".json":
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return {"data": data[:limit], "total": len(data)}
                    return {"data": data, "total": 1}
            elif full_path.suffix == ".csv":
                import csv
                with open(full_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = []
                    for i, row in enumerate(reader):
                        if i >= limit:
                            break
                        rows.append(row)
                    # Re-read to get total count
                    f.seek(0)
                    total = sum(1 for _ in f) - 1
                    return {"data": rows, "total": total}
            elif full_path.suffix.lower() in (".xlsx", ".xls"):
                import pandas as pd
                # Read first limit rows
                df = pd.read_excel(full_path, nrows=limit)
                # Get total row count (only read first column to save memory)
                df_count = pd.read_excel(full_path, usecols=[0])
                total = len(df_count)
                # Convert to list of dictionaries, handle NaN values
                rows = df.where(pd.notnull(df), None).to_dict(orient='records')
                return {
                    "data": rows,
                    "total": total,
                    "columns": list(df.columns)
                }
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type for preview")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON file")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Return file download
        return FileResponse(
            path=full_path,
            filename=full_path.name,
            media_type="application/octet-stream"
        )


@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """Download file"""
    full_path = DATA_DIR / file_path

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    # Security check
    try:
        full_path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(
        path=full_path,
        filename=full_path.name,
        media_type="application/octet-stream"
    )


@router.get("/stats")
async def get_data_stats():
    """Get data statistics"""
    if not DATA_DIR.exists():
        return {"total_files": 0, "total_size": 0, "by_platform": {}, "by_type": {}}

    stats = {
        "total_files": 0,
        "total_size": 0,
        "by_platform": {},
        "by_type": {}
    }

    supported_extensions = {".json", ".csv", ".xlsx", ".xls"}

    for root, dirs, filenames in os.walk(DATA_DIR):
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            if file_path.suffix.lower() not in supported_extensions:
                continue

            try:
                stat = file_path.stat()
                stats["total_files"] += 1
                stats["total_size"] += stat.st_size

                # Statistics by type
                file_type = file_path.suffix[1:].lower()
                stats["by_type"][file_type] = stats["by_type"].get(file_type, 0) + 1

                # Statistics by platform (inferred from path)
                rel_path = str(file_path.relative_to(DATA_DIR))
                for platform in ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]:
                    if platform in rel_path.lower():
                        stats["by_platform"][platform] = stats["by_platform"].get(platform, 0) + 1
                        break
            except Exception:
                continue

    return stats


@router.get("/xhs/overview")
async def get_xhs_overview():
    """Get Xiaohongshu data overview from database."""
    _ensure_db_available()

    try:
        async with get_session() as session:
            if session is None:
                raise HTTPException(status_code=500, detail="Database session is not available")

            creator_total = (
                await session.execute(select(func.count()).select_from(XhsCreator))
            ).scalar_one()
            note_total = (
                await session.execute(select(func.count()).select_from(XhsNote))
            ).scalar_one()
            comment_total = (
                await session.execute(select(func.count()).select_from(XhsNoteComment))
            ).scalar_one()
            notes_with_comments = (
                await session.execute(select(func.count(func.distinct(XhsNoteComment.note_id))))
            ).scalar_one()

            top_creator_rows = (
                await session.execute(
                    select(
                        XhsNote.user_id,
                        XhsNote.nickname,
                        func.count(XhsNote.id).label("note_count"),
                    )
                    .group_by(XhsNote.user_id, XhsNote.nickname)
                    .order_by(func.count(XhsNote.id).desc())
                    .limit(8)
                )
            ).all()

            return {
                "creator_total": creator_total,
                "note_total": note_total,
                "comment_total": comment_total,
                "notes_with_comments": notes_with_comments,
                "top_creators_by_note_count": [
                    {
                        "user_id": user_id,
                        "nickname": nickname,
                        "note_count": note_count,
                    }
                    for user_id, nickname, note_count in top_creator_rows
                ],
            }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Failed to query Xiaohongshu overview")


@router.get("/xhs/creators")
async def get_xhs_creators(page: int = 1, page_size: int = 20, keyword: str = ""):
    """Get Xiaohongshu creator list."""
    _ensure_db_available()
    page, page_size, offset = _normalize_page(page, page_size)
    keyword = keyword.strip()

    try:
        async with get_session() as session:
            if session is None:
                raise HTTPException(status_code=500, detail="Database session is not available")

            conditions = []
            if keyword:
                like_keyword = f"%{keyword}%"
                conditions.append(
                    or_(
                        XhsCreator.user_id.like(like_keyword),
                        XhsCreator.nickname.like(like_keyword),
                        XhsCreator.desc.like(like_keyword),
                        XhsCreator.tag_list.like(like_keyword),
                    )
                )

            query_stmt = select(XhsCreator)
            count_stmt = select(func.count()).select_from(XhsCreator)
            if conditions:
                query_stmt = query_stmt.where(*conditions)
                count_stmt = count_stmt.where(*conditions)

            query_stmt = query_stmt.order_by(
                XhsCreator.last_modify_ts.desc(),
                XhsCreator.add_ts.desc(),
                XhsCreator.id.desc(),
            ).offset(offset).limit(page_size)

            rows = (await session.execute(query_stmt)).scalars().all()
            total = (await session.execute(count_stmt)).scalar_one()

            return {
                "items": [_creator_to_dict(row) for row in rows],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": math.ceil(total / page_size) if total else 0,
                },
            }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Failed to query Xiaohongshu creators")


@router.get("/xhs/notes")
async def get_xhs_notes(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    creator_user_id: str = "",
):
    """Get Xiaohongshu note list."""
    _ensure_db_available()
    page, page_size, offset = _normalize_page(page, page_size)
    keyword = keyword.strip()
    creator_user_id = creator_user_id.strip()

    try:
        async with get_session() as session:
            if session is None:
                raise HTTPException(status_code=500, detail="Database session is not available")

            conditions = []
            if keyword:
                like_keyword = f"%{keyword}%"
                conditions.append(
                    or_(
                        XhsNote.note_id.like(like_keyword),
                        XhsNote.title.like(like_keyword),
                        XhsNote.desc.like(like_keyword),
                        XhsNote.nickname.like(like_keyword),
                        XhsNote.source_keyword.like(like_keyword),
                    )
                )
            if creator_user_id:
                conditions.append(XhsNote.user_id == creator_user_id)

            query_stmt = select(XhsNote)
            count_stmt = select(func.count()).select_from(XhsNote)
            if conditions:
                query_stmt = query_stmt.where(*conditions)
                count_stmt = count_stmt.where(*conditions)

            query_stmt = query_stmt.order_by(
                XhsNote.time.desc(),
                XhsNote.last_modify_ts.desc(),
                XhsNote.id.desc(),
            ).offset(offset).limit(page_size)

            rows = (await session.execute(query_stmt)).scalars().all()
            total = (await session.execute(count_stmt)).scalar_one()

            return {
                "items": [_note_to_dict(row) for row in rows],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": math.ceil(total / page_size) if total else 0,
                },
            }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Failed to query Xiaohongshu notes")


@router.get("/xhs/notes/{note_id}/comments")
async def get_xhs_note_comments(note_id: str, keyword: str = ""):
    """Get Xiaohongshu note comments and attach child comments under root comments."""
    _ensure_db_available()
    note_id = note_id.strip()
    keyword = keyword.strip()

    if not note_id:
        raise HTTPException(status_code=400, detail="note_id is required")

    try:
        async with get_session() as session:
            if session is None:
                raise HTTPException(status_code=500, detail="Database session is not available")

            query_stmt = select(XhsNoteComment).where(XhsNoteComment.note_id == note_id)
            if keyword:
                query_stmt = query_stmt.where(XhsNoteComment.content.like(f"%{keyword}%"))

            query_stmt = query_stmt.order_by(
                XhsNoteComment.create_time.desc(),
                XhsNoteComment.id.desc(),
            )

            rows = (await session.execute(query_stmt)).scalars().all()
            comments = [_comment_to_dict(row) for row in rows]
            root_comments, child_count = _build_comment_tree(comments)

            return {
                "note_id": note_id,
                "total_comments": len(comments),
                "root_comment_count": len(root_comments),
                "child_comment_count": child_count,
                "root_comments": root_comments,
            }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Failed to query Xiaohongshu comments")
