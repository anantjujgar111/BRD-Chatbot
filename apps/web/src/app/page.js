"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  createWorkspace,
  deleteFile,
  generateBrd,
  getStats,
  listFiles,
  sendChat,
  uploadFiles,
} from "../lib/api";

const WORKSPACE_KEY = "brd_workspace_id";

export default function HomePage() {
  const [workspaceId, setWorkspaceId] = useState("");
  const [files, setFiles] = useState([]);
  const [stats, setStats] = useState({ file_count: 0, indexed_files: 0, chunk_count: 0 });
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [brdMarkdown, setBrdMarkdown] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [removingFileId, setRemovingFileId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
  async function bootstrap() {
      try {
        const existing = localStorage.getItem(WORKSPACE_KEY);
        if (existing) {
          setWorkspaceId(existing);
          return;
        }
        const workspace = await createWorkspace("BRD Workspace");
        localStorage.setItem(WORKSPACE_KEY, workspace.id);
        setWorkspaceId(workspace.id);
      } catch (err) {
        setError(err.message);
      }
    }
    bootstrap();
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    refreshFiles();
    const interval = setInterval(refreshFiles, 4000);
    return () => clearInterval(interval);
  }, [workspaceId]);

  async function refreshFiles() {
    if (!workspaceId) return;
    try {
      const [fileList, statData] = await Promise.all([
        listFiles(workspaceId),
        getStats(workspaceId),
      ]);
      setFiles(fileList);
      setStats(statData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onUpload(event) {
    const selected = Array.from(event.target.files || []);
    if (!selected.length || !workspaceId) return;
    setUploading(true);
    setError("");
    try {
      await uploadFiles(workspaceId, selected);
      await refreshFiles();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function onRemoveFile(file) {
    if (!workspaceId || removingFileId) return;
    const confirmed = window.confirm(`Remove "${file.filename}" from chat context?`);
    if (!confirmed) return;

    setRemovingFileId(file.id);
    setError("");
    try {
      await deleteFile(workspaceId, file.id);
      await refreshFiles();
    } catch (err) {
      setError(err.message);
    } finally {
      setRemovingFileId("");
    }
  }

  async function onSend(mode = "qa") {
    if (!workspaceId) return;
    const text = input.trim() || (mode === "brd_full" ? "Generate full BRD" : "");
    if (!text && mode === "qa") return;

    setLoading(true);
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
  setInput("");

    try {
      const response = await sendChat({
        workspace_id: workspaceId,
        message: text,
        mode,
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.answer,
          citations: response.citations || [],
          confidence: response.confidence,
        },
      ]);
      if (mode !== "qa") {
        setBrdMarkdown(response.answer);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function onGenerateBrd() {
    if (!workspaceId) return;
    setLoading(true);
    setError("");
    try {
      const document = await generateBrd(workspaceId, "Business Requirements Document");
      setBrdMarkdown(document.content_markdown);
      setMessages((prev) => [
        ...prev,
        { role: "user", content: "Generate BRD document" },
        {
          role: "assistant",
          content: "BRD generated. See the BRD panel below.",
          citations: [],
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const indexedCount = useMemo(
    () => files.filter((file) => file.status === "indexed").length,
    [files]
  );

  return (
    <main className="app-shell">
      <header className="header">
        <h1>BRD Chatbot</h1>
        <p>
          Upload multiple messy Excel files, ask questions, and generate a Business Requirements
          Document with source citations.
        </p>
      </header>

      <div className="grid">
        <section className="panel">
          <h2>Upload Excel Files</h2>
          <label className="upload-zone">
            <input
              type="file"
              multiple
              accept=".xlsx,.xls,.csv"
              onChange={onUpload}
              disabled={uploading}
              hidden
            />
            {uploading ? "Uploading..." : "Drop or click to upload many Excel/CSV files"}
          </label>

          <div className="stats">
            Files: {stats.file_count} | Indexed: {indexedCount} | Chunks: {stats.chunk_count}
          </div>

          <div className="file-list">
            {files.map((file) => (
              <div key={file.id} className="file-item">
                <span className="file-name" title={file.filename}>
                  {file.filename}
                </span>
                <div className="file-actions">
                  <span className={`status ${file.status}`}>{file.status}</span>
                  <button
                    type="button"
                    className="remove-file"
                    onClick={() => onRemoveFile(file)}
                    disabled={removingFileId === file.id}
                    aria-label={`Remove ${file.filename}`}
                    title="Remove file from context"
                  >
                    {removingFileId === file.id ? "..." : "×"}
                  </button>
                </div>
              </div>
            ))}
            {!files.length && <div className="file-item">No files uploaded yet.</div>}
          </div>
        </section>

        <section className="panel">
          <h2>Chat</h2>
          <div className="actions">
            <button className="secondary" onClick={onGenerateBrd} disabled={loading}>
              Generate Full BRD
            </button>
            <button
              className="secondary"
              onClick={() => onSend("brd_section")}
              disabled={loading || !input.trim()}
            >
              Generate Section From Prompt
            </button>
          </div>

          <div className="chat-log">
            {messages.map((message, index) => (
              <div key={index} className={`message ${message.role}`}>
                <ReactMarkdown>{message.content}</ReactMarkdown>
                {message.citations?.length > 0 && (
                  <div className="citations">
                    <strong>Sources</strong>
                    <ul>
                      {message.citations.map((citation, i) => (
                        <li key={i}>
                          {citation.file} | {citation.sheet} | {citation.cell_range}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
            {!messages.length && (
              <div className="message assistant">
                Upload files, wait for indexing, then ask questions like:
                <br />
                <em>What are the main business requirements across all files?</em>
              </div>
            )}
          </div>

          <div className="chat-input-row">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about requirements, stakeholders, scope, or processes..."
            />
            <button className="primary" onClick={() => onSend("qa")} disabled={loading}>
              {loading ? "Thinking..." : "Send"}
            </button>
          </div>
          {error && <div className="error">{error}</div>}
        </section>
      </div>

      {brdMarkdown && (
        <section className="panel brd-panel">
          <h2>Generated BRD</h2>
          <div className="markdown-output">
            <ReactMarkdown>{brdMarkdown}</ReactMarkdown>
          </div>
        </section>
      )}
    </main>
  );
}
