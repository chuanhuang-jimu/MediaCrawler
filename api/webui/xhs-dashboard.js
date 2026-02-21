const API_BASE = "/api/data/xhs";

const state = {
  creators: { page: 1, pageSize: 12, keyword: "", total: 0, totalPages: 0 },
  notes: { page: 1, pageSize: 12, keyword: "", creatorUserId: "", total: 0, totalPages: 0 },
  comments: { noteId: "", noteTitle: "", keyword: "" },
};

const els = {
  statCreators: document.getElementById("stat-creators"),
  statNotes: document.getElementById("stat-notes"),
  statComments: document.getElementById("stat-comments"),
  statNotesWithComments: document.getElementById("stat-notes-with-comments"),
  topCreators: document.getElementById("top-creators"),
  statusLine: document.getElementById("status-line"),
  creatorTbody: document.getElementById("creator-tbody"),
  creatorPagination: document.getElementById("creator-pagination"),
  noteTbody: document.getElementById("note-tbody"),
  notePagination: document.getElementById("note-pagination"),
  drawer: document.getElementById("comment-drawer"),
  drawerMask: document.getElementById("drawer-mask"),
  drawerTitle: document.getElementById("drawer-title"),
  commentList: document.getElementById("comment-list"),
  commentMeta: document.getElementById("comment-meta"),
};

function escapeHtml(raw) {
  const text = raw == null ? "" : String(raw);
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtCount(value) {
  const n = Number(value);
  if (Number.isNaN(n)) {
    return value || "-";
  }
  return n.toLocaleString("zh-CN");
}

function fmtTime(ts) {
  if (!ts) return "-";
  const n = Number(ts);
  if (Number.isNaN(n)) return escapeHtml(ts);
  const ms = n > 1000000000000 ? n : n * 1000;
  const d = new Date(ms);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("zh-CN", { hour12: false });
}

function textInitial(text) {
  if (!text) return "?";
  return String(text).trim().slice(0, 1).toUpperCase();
}

function splitTags(tagsRaw) {
  if (!tagsRaw) return [];
  const text = String(tagsRaw).replaceAll("[", "").replaceAll("]", "").replaceAll('"', "");
  return text
    .split(/[,\s，]+/)
    .map((i) => i.trim())
    .filter(Boolean)
    .slice(0, 4);
}

async function fetchJson(url) {
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(payload.detail || `请求失败 (${resp.status})`);
  }
  return payload;
}

function setStatus(message = "", isError = false) {
  els.statusLine.textContent = message;
  els.statusLine.style.color = isError ? "#9d2e10" : "#6b6052";
}

function setLoading(targetEl, colSpan) {
  targetEl.innerHTML = `<tr><td colspan="${colSpan}" class="empty">加载中...</td></tr>`;
}

function renderPagination(el, page, totalPages, total, onPrev, onNext) {
  el.innerHTML = `
    <span>共 ${fmtCount(total)} 条</span>
    <span>第 ${totalPages === 0 ? 0 : page} / ${totalPages} 页</span>
    <button class="mini-btn" ${page <= 1 ? "disabled" : ""} data-role="prev">上一页</button>
    <button class="mini-btn" ${page >= totalPages || totalPages === 0 ? "disabled" : ""} data-role="next">下一页</button>
  `;

  const prevBtn = el.querySelector('[data-role="prev"]');
  const nextBtn = el.querySelector('[data-role="next"]');
  if (prevBtn) prevBtn.addEventListener("click", onPrev);
  if (nextBtn) nextBtn.addEventListener("click", onNext);
}

function renderOverview(data) {
  els.statCreators.textContent = fmtCount(data.creator_total ?? 0);
  els.statNotes.textContent = fmtCount(data.note_total ?? 0);
  els.statComments.textContent = fmtCount(data.comment_total ?? 0);
  els.statNotesWithComments.textContent = fmtCount(data.notes_with_comments ?? 0);

  const topList = data.top_creators_by_note_count || [];
  if (!topList.length) {
    els.topCreators.className = "top-list empty";
    els.topCreators.innerHTML = "暂无数据";
    return;
  }

  els.topCreators.className = "top-list";
  const maxCount = Math.max(...topList.map((row) => Number(row.note_count) || 0), 1);
  els.topCreators.innerHTML = topList
    .map((row) => {
      const count = Number(row.note_count) || 0;
      const width = Math.max(5, Math.round((count / maxCount) * 100));
      return `
        <div class="top-item">
          <div class="top-item-meta">
            <span>${escapeHtml(row.nickname || row.user_id || "未知用户")}</span>
            <span>${fmtCount(count)} 篇</span>
          </div>
          <div class="bar-track"><div class="bar" style="width:${width}%"></div></div>
          <div class="small muted mono">${escapeHtml(row.user_id || "-")}</div>
        </div>
      `;
    })
    .join("");
}

function renderCreatorRows(items) {
  if (!items.length) {
    els.creatorTbody.innerHTML = `<tr><td colspan="7" class="empty">没有匹配的 creator</td></tr>`;
    return;
  }

  els.creatorTbody.innerHTML = items
    .map((row) => {
      const tags = splitTags(row.tag_list)
        .map((tag) => `<span class="tag-pill">${escapeHtml(tag)}</span>`)
        .join("");
      return `
        <tr>
          <td>
            <div class="cell-main">
              ${
                row.avatar
                  ? `<img class="avatar" src="${escapeHtml(row.avatar)}" alt="" loading="lazy" />`
                  : `<span class="avatar-fallback">${escapeHtml(textInitial(row.nickname))}</span>`
              }
              <div>
                <div>${escapeHtml(row.nickname || "未知昵称")}</div>
                <div class="mono muted">${escapeHtml(row.user_id || "-")}</div>
              </div>
            </div>
          </td>
          <td>${escapeHtml(row.fans || "-")}</td>
          <td>${escapeHtml(row.follows || "-")}</td>
          <td>${escapeHtml(row.interaction || "-")}</td>
          <td>${tags || '<span class="muted small">-</span>'}</td>
          <td class="small muted">${fmtTime(row.last_modify_ts || row.add_ts)}</td>
          <td><button class="mini-btn" data-role="filter-notes" data-user-id="${escapeHtml(row.user_id || "")}">看 TA 的 notes</button></td>
        </tr>
      `;
    })
    .join("");

  els.creatorTbody.querySelectorAll('button[data-role="filter-notes"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      const userId = btn.getAttribute("data-user-id") || "";
      document.getElementById("note-creator-user-id").value = userId;
      state.notes.creatorUserId = userId;
      state.notes.page = 1;
      loadNotes();
    });
  });
}

function renderNoteRows(items) {
  if (!items.length) {
    els.noteTbody.innerHTML = `<tr><td colspan="5" class="empty">没有匹配的 note</td></tr>`;
    return;
  }

  els.noteTbody.innerHTML = items
    .map((row) => {
      const title = row.title || row.desc || "(无标题)";
      return `
        <tr>
          <td>
            <div><b>${escapeHtml(title)}</b></div>
            <div class="mono muted">${escapeHtml(row.note_id || "-")}</div>
            ${
              row.note_url
                ? `<a class="small" target="_blank" rel="noopener noreferrer" href="${escapeHtml(row.note_url)}">打开原始链接</a>`
                : '<span class="small muted">无链接</span>'
            }
          </td>
          <td>
            <div>${escapeHtml(row.nickname || "未知作者")}</div>
            <div class="mono muted">${escapeHtml(row.user_id || "-")}</div>
          </td>
          <td>
            <div class="metric-list">
              <span>赞 <b>${escapeHtml(row.liked_count || "0")}</b></span>
              <span>藏 <b>${escapeHtml(row.collected_count || "0")}</b></span>
              <span>评 <b>${escapeHtml(row.comment_count || "0")}</b></span>
              <span>转 <b>${escapeHtml(row.share_count || "0")}</b></span>
            </div>
          </td>
          <td class="small muted">${fmtTime(row.time || row.last_update_time)}</td>
          <td>
            <button class="mini-btn callout" data-role="open-comments" data-note-id="${encodeURIComponent(
              row.note_id || "",
            )}" data-note-title="${encodeURIComponent(title)}">
              查看评论
            </button>
          </td>
        </tr>
      `;
    })
    .join("");

  els.noteTbody.querySelectorAll('button[data-role="open-comments"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      const noteId = decodeURIComponent(btn.getAttribute("data-note-id") || "");
      const noteTitle = decodeURIComponent(btn.getAttribute("data-note-title") || "");
      openCommentDrawer(noteId, noteTitle);
    });
  });
}

function renderCommentCard(comment) {
  const author = comment.nickname || comment.user_id || "匿名用户";
  const children = comment.sub_comments || [];
  return `
    <article class="comment-card">
      <div class="comment-header">
        ${
          comment.avatar
            ? `<img class="avatar" src="${escapeHtml(comment.avatar)}" alt="" loading="lazy" />`
            : `<span class="avatar-fallback">${escapeHtml(textInitial(author))}</span>`
        }
        <div>
          <div>${escapeHtml(author)}</div>
          <div class="small muted">👍 ${escapeHtml(comment.like_count || "0")} · ${fmtTime(comment.create_time)}</div>
        </div>
      </div>
      <div class="comment-content">${escapeHtml(comment.content || "").replaceAll("\n", "<br />")}</div>
      ${
        children.length
          ? `<div class="comment-children">${children.map((child) => renderCommentCard(child)).join("")}</div>`
          : ""
      }
    </article>
  `;
}

function renderComments(data) {
  const roots = data.root_comments || [];
  if (!roots.length) {
    els.commentList.innerHTML = '<p class="empty">当前 note 没有评论数据，或筛选后为空。</p>';
  } else {
    els.commentList.innerHTML = roots.map((comment) => renderCommentCard(comment)).join("");
  }
  els.commentMeta.textContent = `共 ${fmtCount(data.total_comments || 0)} 条评论；一级 ${fmtCount(
    data.root_comment_count || 0,
  )} 条；子评论 ${fmtCount(data.child_comment_count || 0)} 条`;
}

async function loadOverview() {
  const data = await fetchJson(`${API_BASE}/overview`);
  renderOverview(data);
}

async function loadCreators() {
  setLoading(els.creatorTbody, 7);
  const q = new URLSearchParams({
    page: String(state.creators.page),
    page_size: String(state.creators.pageSize),
    keyword: state.creators.keyword,
  });
  const data = await fetchJson(`${API_BASE}/creators?${q.toString()}`);
  const pageInfo = data.pagination || {};
  state.creators.total = pageInfo.total || 0;
  state.creators.totalPages = pageInfo.total_pages || 0;
  state.creators.page = pageInfo.page || state.creators.page;
  renderCreatorRows(data.items || []);
  renderPagination(
    els.creatorPagination,
    state.creators.page,
    state.creators.totalPages,
    state.creators.total,
    () => {
      state.creators.page -= 1;
      loadCreators().catch(showError);
    },
    () => {
      state.creators.page += 1;
      loadCreators().catch(showError);
    },
  );
}

async function loadNotes() {
  setLoading(els.noteTbody, 5);
  const q = new URLSearchParams({
    page: String(state.notes.page),
    page_size: String(state.notes.pageSize),
    keyword: state.notes.keyword,
    creator_user_id: state.notes.creatorUserId,
  });
  const data = await fetchJson(`${API_BASE}/notes?${q.toString()}`);
  const pageInfo = data.pagination || {};
  state.notes.total = pageInfo.total || 0;
  state.notes.totalPages = pageInfo.total_pages || 0;
  state.notes.page = pageInfo.page || state.notes.page;
  renderNoteRows(data.items || []);
  renderPagination(
    els.notePagination,
    state.notes.page,
    state.notes.totalPages,
    state.notes.total,
    () => {
      state.notes.page -= 1;
      loadNotes().catch(showError);
    },
    () => {
      state.notes.page += 1;
      loadNotes().catch(showError);
    },
  );
}

function openCommentDrawer(noteId, noteTitle) {
  if (!noteId) return;
  state.comments.noteId = noteId;
  state.comments.noteTitle = noteTitle || noteId;
  state.comments.keyword = "";
  document.getElementById("comment-keyword").value = "";
  els.drawerTitle.textContent = `评论详情 - ${state.comments.noteTitle}`;
  els.commentList.innerHTML = '<p class="empty">加载评论中...</p>';
  els.commentMeta.textContent = "";
  els.drawer.classList.add("open");
  els.drawerMask.classList.add("open");
  loadComments().catch(showError);
}

function closeCommentDrawer() {
  els.drawer.classList.remove("open");
  els.drawerMask.classList.remove("open");
}

async function loadComments() {
  if (!state.comments.noteId) return;
  const q = new URLSearchParams({ keyword: state.comments.keyword });
  const data = await fetchJson(`${API_BASE}/notes/${encodeURIComponent(state.comments.noteId)}/comments?${q}`);
  renderComments(data);
}

function showError(err) {
  setStatus(err instanceof Error ? err.message : "发生未知错误", true);
}

function bindEvents() {
  document.getElementById("refresh-overview").addEventListener("click", () => {
    loadOverview()
      .then(() => setStatus("统计已更新"))
      .catch(showError);
  });

  document.getElementById("creator-search-btn").addEventListener("click", () => {
    state.creators.keyword = document.getElementById("creator-keyword").value.trim();
    state.creators.page = 1;
    loadCreators().catch(showError);
  });

  document.getElementById("note-search-btn").addEventListener("click", () => {
    state.notes.keyword = document.getElementById("note-keyword").value.trim();
    state.notes.creatorUserId = document.getElementById("note-creator-user-id").value.trim();
    state.notes.page = 1;
    loadNotes().catch(showError);
  });

  document.getElementById("creator-keyword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("creator-search-btn").click();
  });
  document.getElementById("note-keyword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("note-search-btn").click();
  });
  document.getElementById("note-creator-user-id").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("note-search-btn").click();
  });

  document.getElementById("comment-search-btn").addEventListener("click", () => {
    state.comments.keyword = document.getElementById("comment-keyword").value.trim();
    loadComments().catch(showError);
  });
  document.getElementById("comment-keyword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("comment-search-btn").click();
  });

  document.getElementById("drawer-close").addEventListener("click", closeCommentDrawer);
  els.drawerMask.addEventListener("click", closeCommentDrawer);
}

async function bootstrap() {
  bindEvents();
  setStatus("正在加载数据...");
  try {
    await Promise.all([loadOverview(), loadCreators(), loadNotes()]);
    setStatus("数据加载完成");
  } catch (err) {
    showError(err);
  }
}

bootstrap();
