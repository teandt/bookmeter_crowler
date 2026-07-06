import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bookmeter_crawl
from sqlalchemy import and_, or_


logger = logging.getLogger("bookmeter_web")

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "csv" / "booklog.csv"


class JobLogHandler(logging.Handler):
    def __init__(self, job):
        super().__init__()
        self.job = job
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record):
        try:
            self.job.add_log(self.format(record))
        except Exception:
            pass


class Job:
    def __init__(self, name):
        self.name = name
        self.status = "queued"
        self.started_at = None
        self.finished_at = None
        self.error = None
        self.result = None
        self.logs = []
        self.lock = threading.Lock()

    def add_log(self, message):
        with self.lock:
            self.logs.append(message)

    def snapshot(self):
        with self.lock:
            return {
                "name": self.name,
                "status": self.status,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "result": self.result,
                "logs": list(self.logs),
            }


class JobManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.current = None

    def status(self):
        with self.lock:
            if self.current is None:
                return {
                    "running": False,
                    "job": None,
                }
            snapshot = self.current.snapshot()
            return {
                "running": snapshot["status"] in {"queued", "running"},
                "job": snapshot,
            }

    def start(self, name, target):
        with self.lock:
            if self.current and self.current.snapshot()["status"] in {"queued", "running"}:
                raise RuntimeError("別の処理が実行中です。完了後に再実行してください。")

            job = Job(name)
            self.current = job
            thread = threading.Thread(target=self._run, args=(job, target), daemon=True)
            thread.start()
            return job.snapshot()

    def _run(self, job, target):
        handler = JobLogHandler(job)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        with job.lock:
            job.status = "running"
            job.started_at = datetime.now().isoformat(timespec="seconds")
        job.add_log(f"{job.name} を開始しました。")

        try:
            result = target()
            with job.lock:
                job.status = "succeeded"
                job.result = result
        except Exception as exc:
            with job.lock:
                job.status = "failed"
                job.error = str(exc)
            job.add_log(traceback.format_exc())
        finally:
            with job.lock:
                job.finished_at = datetime.now().isoformat(timespec="seconds")
            job.add_log(f"{job.name} を終了しました。")
            root_logger.removeHandler(handler)


JOB_MANAGER = JobManager()


def make_crawl_args(options):
    all_selected = bool(options.get("all"))
    args = argparse.Namespace(
        stacked=bool(options.get("stacked")) or all_selected,
        read=bool(options.get("read")) or all_selected,
        detail=bool(options.get("detail")) or all_selected,
        all=all_selected,
        checkstacked=False,
        checkread=False,
        checkdetail=False,
        deletedetail=False,
        csv=False,
        search=None,
        target="all",
    )
    if not (args.stacked or args.read or args.detail):
        raise ValueError("少なくとも1つの取得対象を選択してください。")
    return args


def run_crawl_job(options):
    args = make_crawl_args(options)
    bookmeter_crawl.initialize_database()

    command = [sys.executable, str(BASE_DIR / "bookmeter_crawl.py")]
    if args.all:
        command.append("--all")
    else:
        if args.stacked:
            command.append("--stacked")
        if args.read:
            command.append("--read")
        if args.detail:
            command.append("--detail")

    job_logger = logging.getLogger("bookmeter_crawl")
    job_logger.info("CLI を起動します: %s", " ".join(command))
    process = subprocess.Popen(
        command,
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        job_logger.info(line.rstrip())
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"クロール処理が失敗しました。終了コード: {return_code}")

    return {
        "stacked": args.stacked,
        "read": args.read,
        "detail": args.detail,
    }


def run_csv_job():
    bookmeter_crawl.initialize_database()
    bookmeter_crawl.handle_csv_export()
    return {
        "path": str(CSV_PATH),
        "exists": CSV_PATH.exists(),
    }


def row_value(value):
    return "" if value is None else value


def detail_to_dict(detail):
    if detail is None:
        return None
    return {
        "book_id": row_value(detail.book_id),
        "title": row_value(detail.title),
        "pages": row_value(detail.pages),
        "amazon_url": row_value(detail.amazon_url),
        "asin": row_value(detail.asin),
    }


def list_entry_to_dict(entry, detail=None, label=None):
    data = {
        "num": entry.num,
        "book_id": row_value(entry.book_id),
        "title": row_value(entry.title),
        "authors": row_value(entry.authors),
        "date": row_value(entry.date),
        "url": row_value(entry.url),
        "detail": detail_to_dict(detail),
    }
    if label:
        data["label"] = label
    return data


def get_books(kind):
    bookmeter_crawl.initialize_database()
    with bookmeter_crawl.session_scope() as session:
        if kind == "read":
            rows = (
                session.query(bookmeter_crawl.ReadBooks, bookmeter_crawl.BookDetail)
                .outerjoin(
                    bookmeter_crawl.BookDetail,
                    bookmeter_crawl.ReadBooks.book_id == bookmeter_crawl.BookDetail.book_id,
                )
                .order_by(bookmeter_crawl.ReadBooks.num)
                .all()
            )
            items = [list_entry_to_dict(book, detail, "読") for book, detail in rows]
        elif kind == "stacked":
            rows = (
                session.query(bookmeter_crawl.StackedBooks, bookmeter_crawl.BookDetail)
                .outerjoin(
                    bookmeter_crawl.BookDetail,
                    bookmeter_crawl.StackedBooks.book_id == bookmeter_crawl.BookDetail.book_id,
                )
                .order_by(bookmeter_crawl.StackedBooks.num)
                .all()
            )
            items = [list_entry_to_dict(book, detail, "積") for book, detail in rows]
        elif kind == "detail":
            rows = session.query(bookmeter_crawl.BookDetail).order_by(bookmeter_crawl.BookDetail.title).all()
            items = [detail_to_dict(detail) for detail in rows]
        else:
            raise ValueError("kind は read, stacked, detail のいずれかを指定してください。")
    return {"kind": kind, "count": len(items), "items": items}


def roman_to_int(text):
    roman_values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev_value = 0
    for char in reversed(text):
        value = roman_values.get(char, 0)
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value
    return total


def natural_keys(text):
    import re

    lookahead = r"(?=$|\s|\(|[^A-Za-z])"
    roman = r"[IVX]+"
    pattern = f"(\\d+|(?<=^){roman}{lookahead}|(?<=[^A-Za-z]){roman}{lookahead}|(?<=S){roman}{lookahead})"
    return [
        int(part)
        if part.isdigit()
        else roman_to_int(part)
        if re.fullmatch(roman, part)
        else part
        for part in re.split(pattern, text)
        if part
    ]


def search_books(keywords, target):
    if target not in {"all", "read", "stacked"}:
        raise ValueError("target は all, read, stacked のいずれかを指定してください。")
    if not keywords:
        raise ValueError("キーワードを1件以上入力してください。")

    bookmeter_crawl.initialize_database()
    with bookmeter_crawl.session_scope() as session:
        results = []

        def get_query_results(model_class, label):
            query = session.query(model_class, bookmeter_crawl.BookDetail).join(
                bookmeter_crawl.BookDetail,
                model_class.book_id == bookmeter_crawl.BookDetail.book_id,
            )
            conditions = [bookmeter_crawl.BookDetail.title.like(f"%{keyword}%") for keyword in keywords]
            rows = query.filter(and_(*conditions)).all()
            return [
                {
                    "label": label,
                    "title": row_value(detail.title),
                    "authors": row_value(book.authors),
                    "date": row_value(getattr(book, "date", None)),
                    "book_id": row_value(book.book_id),
                    "url": f"https://bookmeter.com/books/{book.book_id}",
                }
                for book, detail in rows
            ]

        if target in {"all", "read"}:
            results.extend(get_query_results(bookmeter_crawl.ReadBooks, "読"))
        if target in {"all", "stacked"}:
            results.extend(get_query_results(bookmeter_crawl.StackedBooks, "積"))

    results.sort(key=lambda item: natural_keys(item["title"]), reverse=True)
    return {"target": target, "keywords": keywords, "count": len(results), "items": results}


def preview_delete_details():
    bookmeter_crawl.initialize_database()
    with bookmeter_crawl.session_scope() as session:
        rows = (
            session.query(bookmeter_crawl.BookDetail)
            .outerjoin(bookmeter_crawl.ReadBooks, bookmeter_crawl.BookDetail.book_id == bookmeter_crawl.ReadBooks.book_id)
            .outerjoin(
                bookmeter_crawl.StackedBooks,
                bookmeter_crawl.BookDetail.book_id == bookmeter_crawl.StackedBooks.book_id,
            )
            .filter(bookmeter_crawl.ReadBooks.book_id.is_(None), bookmeter_crawl.StackedBooks.book_id.is_(None))
            .order_by(bookmeter_crawl.BookDetail.title)
            .all()
        )
        items = [detail_to_dict(detail) for detail in rows]
    return {"count": len(items), "items": items}


def delete_details_job():
    before = preview_delete_details()
    bookmeter_crawl.handle_delete_details()
    return {"deleted_count": before["count"], "deleted_items": before["items"]}


def csv_validation_status():
    bookmeter_crawl.initialize_database()
    with bookmeter_crawl.session_scope() as session:
        missing_read_count = (
            session.query(bookmeter_crawl.ReadBooks)
            .outerjoin(
                bookmeter_crawl.BookDetail,
                bookmeter_crawl.ReadBooks.book_id == bookmeter_crawl.BookDetail.book_id,
            )
            .filter(bookmeter_crawl.BookDetail.book_id.is_(None))
            .count()
        )
        missing_stacked_count = (
            session.query(bookmeter_crawl.StackedBooks)
            .outerjoin(
                bookmeter_crawl.BookDetail,
                bookmeter_crawl.StackedBooks.book_id == bookmeter_crawl.BookDetail.book_id,
            )
            .filter(bookmeter_crawl.BookDetail.book_id.is_(None))
            .count()
        )
        missing_read_asin_count = (
            session.query(bookmeter_crawl.ReadBooks)
            .join(
                bookmeter_crawl.BookDetail,
                bookmeter_crawl.ReadBooks.book_id == bookmeter_crawl.BookDetail.book_id,
            )
            .filter(or_(bookmeter_crawl.BookDetail.asin.is_(None), bookmeter_crawl.BookDetail.asin == ""))
            .count()
        )
        missing_stacked_asin_count = (
            session.query(bookmeter_crawl.StackedBooks)
            .join(
                bookmeter_crawl.BookDetail,
                bookmeter_crawl.StackedBooks.book_id == bookmeter_crawl.BookDetail.book_id,
            )
            .filter(or_(bookmeter_crawl.BookDetail.asin.is_(None), bookmeter_crawl.BookDetail.asin == ""))
            .count()
        )

    valid = not any(
        (
            missing_read_count,
            missing_stacked_count,
            missing_read_asin_count,
            missing_stacked_asin_count,
        )
    )
    return {
        "valid": valid,
        "missing_read_detail": missing_read_count,
        "missing_stacked_detail": missing_stacked_count,
        "missing_read_asin": missing_read_asin_count,
        "missing_stacked_asin": missing_stacked_asin_count,
        "csv_exists": CSV_PATH.exists(),
        "csv_path": str(CSV_PATH),
    }


INDEX_HTML = r"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bookmeter Crawler</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #65717f;
      --line: #d9dee5;
      --primary: #1f6f8b;
      --primary-dark: #195b73;
      --danger: #b3342f;
      --ok: #287a43;
      --warn: #a8661b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: #ffffff;
      padding: 16px 24px;
      position: sticky;
      top: 0;
      z-index: 5;
    }
    header h1 {
      font-size: 20px;
      margin: 0 0 4px;
      letter-spacing: 0;
    }
    header p { margin: 0; color: var(--muted); }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 24px auto 40px;
      display: grid;
      gap: 20px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }
    h2 {
      font-size: 17px;
      margin: 0 0 14px;
      letter-spacing: 0;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }
    .row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    label {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      min-height: 36px;
    }
    input[type="text"], select {
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 10px;
      font: inherit;
      background: #fff;
      min-width: 180px;
    }
    input[type="text"] { flex: 1 1 260px; }
    button, .download {
      min-height: 38px;
      border: 1px solid var(--primary);
      border-radius: 6px;
      background: var(--primary);
      color: #fff;
      padding: 7px 12px;
      font: inherit;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }
    button:hover, .download:hover { background: var(--primary-dark); }
    button.secondary {
      color: var(--primary);
      background: #fff;
    }
    button.secondary:hover { background: #eef6f9; }
    button.danger {
      background: var(--danger);
      border-color: var(--danger);
    }
    button:disabled {
      opacity: .55;
      cursor: not-allowed;
    }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      border-radius: 999px;
      padding: 4px 10px;
      background: #eef1f4;
      color: var(--muted);
      font-size: 13px;
    }
    .status.running { background: #fff3d8; color: var(--warn); }
    .status.succeeded { background: #e9f6ee; color: var(--ok); }
    .status.failed { background: #fdecea; color: var(--danger); }
    .log {
      height: 220px;
      overflow: auto;
      background: #111820;
      color: #d8e0e8;
      border-radius: 6px;
      padding: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      white-space: pre-wrap;
    }
    .tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      max-height: 420px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 780px;
      background: #fff;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: #f0f3f6;
      font-weight: 600;
    }
    td a { color: var(--primary-dark); }
    .muted { color: var(--muted); }
    .message {
      color: var(--muted);
      margin: 8px 0 0;
    }
    @media (max-width: 720px) {
      header { padding: 14px 16px; }
      main { width: calc(100vw - 20px); margin-top: 12px; }
      section { padding: 14px; }
      button, .download { width: 100%; }
      .row { align-items: stretch; }
      label { width: 100%; }
      input[type="text"], select { width: 100%; min-width: 0; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Bookmeter Crawler</h1>
    <p>読書メーター取得、DB確認、検索、CSV出力</p>
  </header>
  <main>
    <section>
      <h2>実行</h2>
      <div class="row">
        <label><input id="run-stacked" type="checkbox">積読本</label>
        <label><input id="run-read" type="checkbox">読んだ本</label>
        <label><input id="run-detail" type="checkbox">書籍詳細</label>
        <button id="run-selected">選択して実行</button>
        <button id="run-all" class="secondary">すべて取得</button>
      </div>
      <p class="message">クロール中は他の処理を開始できません。</p>
    </section>

    <section>
      <h2>状態とログ</h2>
      <div class="row">
        <span id="job-status" class="status">待機中</span>
        <span id="job-name" class="muted"></span>
      </div>
      <pre id="job-log" class="log"></pre>
    </section>

    <div class="grid">
      <section>
        <h2>CSV出力</h2>
        <div class="row">
          <button id="csv-check" class="secondary">前提条件を確認</button>
          <button id="csv-export">CSV出力</button>
          <a id="csv-download" class="download" href="/api/download/csv">CSV取得</a>
        </div>
        <p id="csv-message" class="message"></p>
      </section>

      <section>
        <h2>不要詳細データ削除</h2>
        <div class="row">
          <button id="delete-preview" class="secondary">削除対象を確認</button>
          <button id="delete-run" class="danger">確認して削除</button>
        </div>
        <p id="delete-message" class="message"></p>
      </section>
    </div>

    <section>
      <h2>検索</h2>
      <div class="row">
        <input id="search-keywords" type="text" placeholder="キーワードをスペース区切りで入力">
        <select id="search-target">
          <option value="all">読んだ本と積読本</option>
          <option value="read">読んだ本</option>
          <option value="stacked">積読本</option>
        </select>
        <button id="search-run">検索</button>
      </div>
      <p id="search-message" class="message"></p>
      <div id="search-results" class="table-wrap"></div>
    </section>

    <section>
      <h2>DB確認</h2>
      <div class="tabs">
        <button class="secondary" data-kind="read">読んだ本</button>
        <button class="secondary" data-kind="stacked">積読本</button>
        <button class="secondary" data-kind="detail">書籍詳細</button>
      </div>
      <p id="books-message" class="message"></p>
      <div id="books-table" class="table-wrap"></div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const statusEl = $("job-status");
    const logEl = $("job-log");
    const jobNameEl = $("job-name");
    const buttons = Array.from(document.querySelectorAll("button"));

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: {"Content-Type": "application/json"},
        ...options
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      return data;
    }

    function setBusy(running) {
      buttons.forEach((button) => {
        button.disabled = running;
      });
    }

    async function refreshStatus() {
      try {
        const data = await api("/api/status");
        const job = data.job;
        if (!job) {
          statusEl.textContent = "待機中";
          statusEl.className = "status";
          jobNameEl.textContent = "";
          setBusy(false);
          return;
        }
        statusEl.textContent = job.status;
        statusEl.className = `status ${job.status}`;
        jobNameEl.textContent = job.name || "";
        logEl.textContent = (job.logs || []).join("\n");
        logEl.scrollTop = logEl.scrollHeight;
        setBusy(data.running);
      } catch (error) {
        statusEl.textContent = error.message;
        statusEl.className = "status failed";
      }
    }

    async function startJob(path, payload) {
      try {
        await api(path, {method: "POST", body: JSON.stringify(payload || {})});
        await refreshStatus();
      } catch (error) {
        alert(error.message);
      }
    }

    $("run-selected").addEventListener("click", () => {
      startJob("/api/run", {
        stacked: $("run-stacked").checked,
        read: $("run-read").checked,
        detail: $("run-detail").checked
      });
    });
    $("run-all").addEventListener("click", () => startJob("/api/run", {all: true}));
    $("csv-export").addEventListener("click", () => startJob("/api/csv", {}));
    $("delete-run").addEventListener("click", async () => {
      const preview = await api("/api/delete-details/preview");
      if (!preview.count) {
        $("delete-message").textContent = "削除対象はありません。";
        return;
      }
      const ok = confirm(`${preview.count} 件の不要な書籍詳細データを削除します。実行しますか？`);
      if (ok) startJob("/api/delete-details", {});
    });

    $("csv-check").addEventListener("click", async () => {
      try {
        const data = await api("/api/csv/status");
        const parts = [
          data.valid ? "CSV出力できます。" : "CSV出力に必要なデータが不足しています。",
          `読んだ本詳細不足: ${data.missing_read_detail}`,
          `積読本詳細不足: ${data.missing_stacked_detail}`,
          `読んだ本ASIN不足: ${data.missing_read_asin}`,
          `積読本ASIN不足: ${data.missing_stacked_asin}`
        ];
        $("csv-message").textContent = parts.join(" / ");
      } catch (error) {
        $("csv-message").textContent = error.message;
      }
    });

    $("delete-preview").addEventListener("click", async () => {
      try {
        const data = await api("/api/delete-details/preview");
        $("delete-message").textContent = data.count
          ? `${data.count} 件: ${data.items.map((item) => item.title || item.book_id).join(", ")}`
          : "削除対象はありません。";
      } catch (error) {
        $("delete-message").textContent = error.message;
      }
    });

    function renderTable(container, columns, items) {
      if (!items.length) {
        container.innerHTML = "<p class='message'>データはありません。</p>";
        return;
      }
      const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[char]));
      const head = columns.map((col) => `<th>${escape(col.label)}</th>`).join("");
      const body = items.map((item) => {
        const cells = columns.map((col) => {
          const value = col.value(item);
          return `<td>${value && col.html ? value : escape(value)}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
      container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    $("search-run").addEventListener("click", async () => {
      const keywords = $("search-keywords").value.trim();
      if (!keywords) {
        $("search-message").textContent = "キーワードを入力してください。";
        return;
      }
      try {
        const params = new URLSearchParams({q: keywords, target: $("search-target").value});
        const data = await api(`/api/search?${params}`);
        $("search-message").textContent = `${data.count} 件見つかりました。`;
        renderTable($("search-results"), [
          {label: "区分", value: (item) => item.label},
          {label: "タイトル", value: (item) => item.title},
          {label: "著者", value: (item) => item.authors},
          {label: "日付", value: (item) => item.date},
          {label: "URL", html: true, value: (item) => `<a href="${item.url}" target="_blank" rel="noreferrer">${item.url}</a>`}
        ], data.items);
      } catch (error) {
        $("search-message").textContent = error.message;
      }
    });

    async function loadBooks(kind) {
      try {
        const data = await api(`/api/books?kind=${kind}`);
        $("books-message").textContent = `${data.count} 件`;
        if (kind === "detail") {
          renderTable($("books-table"), [
            {label: "book_id", value: (item) => item.book_id},
            {label: "タイトル", value: (item) => item.title},
            {label: "ページ数", value: (item) => item.pages},
            {label: "ASIN", value: (item) => item.asin},
            {label: "Amazon URL", value: (item) => item.amazon_url}
          ], data.items);
        } else {
          renderTable($("books-table"), [
            {label: "num", value: (item) => item.num},
            {label: "区分", value: (item) => item.label},
            {label: "タイトル", value: (item) => item.title},
            {label: "詳細タイトル", value: (item) => item.detail ? item.detail.title : ""},
            {label: "著者", value: (item) => item.authors},
            {label: "日付", value: (item) => item.date},
            {label: "ASIN", value: (item) => item.detail ? item.detail.asin : ""},
            {label: "URL", html: true, value: (item) => item.url ? `<a href="${item.url}" target="_blank" rel="noreferrer">${item.url}</a>` : ""}
          ], data.items);
        }
      } catch (error) {
        $("books-message").textContent = error.message;
      }
    }

    document.querySelectorAll("[data-kind]").forEach((button) => {
      button.addEventListener("click", () => loadBooks(button.dataset.kind));
    });

    refreshStatus();
    loadBooks("read");
    setInterval(refreshStatus, 2000);
  </script>
</body>
</html>
"""


class WebHandler(BaseHTTPRequestHandler):
    server_version = "BookmeterWeb/1.0"

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)

    def dispatch(self, method):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if method == "GET" and path == "/":
                self.send_html(INDEX_HTML)
            elif method == "GET" and path == "/api/status":
                self.send_json(JOB_MANAGER.status())
            elif method == "POST" and path == "/api/run":
                payload = self.read_json()
                self.send_json(JOB_MANAGER.start("クロール", lambda: run_crawl_job(payload)), HTTPStatus.ACCEPTED)
            elif method == "POST" and path == "/api/csv":
                self.send_json(JOB_MANAGER.start("CSV出力", run_csv_job), HTTPStatus.ACCEPTED)
            elif method == "GET" and path == "/api/csv/status":
                self.ensure_not_running()
                self.send_json(csv_validation_status())
            elif method == "GET" and path == "/api/download/csv":
                self.send_csv()
            elif method == "GET" and path == "/api/books":
                self.ensure_not_running()
                params = parse_qs(parsed.query)
                self.send_json(get_books(params.get("kind", ["read"])[0]))
            elif method == "GET" and path == "/api/search":
                self.ensure_not_running()
                params = parse_qs(parsed.query)
                q = params.get("q", [""])[0].strip()
                target = params.get("target", ["all"])[0]
                keywords = [keyword for keyword in q.split() if keyword]
                self.send_json(search_books(keywords, target))
            elif method == "GET" and path == "/api/delete-details/preview":
                self.ensure_not_running()
                self.send_json(preview_delete_details())
            elif method == "POST" and path == "/api/delete-details":
                self.send_json(JOB_MANAGER.start("不要詳細データ削除", delete_details_job), HTTPStatus.ACCEPTED)
            else:
                self.send_json({"error": "Not Found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except Exception as exc:
            logger.exception("request failed")
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def ensure_not_running(self):
        if JOB_MANAGER.status()["running"]:
            raise RuntimeError("別の処理が実行中です。完了後に再実行してください。")

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self):
        if not CSV_PATH.exists():
            self.send_json({"error": "CSVファイルがありません。先にCSV出力を実行してください。"}, HTTPStatus.NOT_FOUND)
            return
        body = CSV_PATH.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=shift_jis")
        self.send_header("Content-Disposition", 'attachment; filename="booklog.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Bookmeter Crawler Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    os.chdir(BASE_DIR)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    server = ThreadingHTTPServer((args.host, args.port), WebHandler)
    logger.info("Web UI を開始しました: http://%s:%s/", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Web UI を停止します。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
