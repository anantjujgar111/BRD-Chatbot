import cors from "cors";
import dotenv from "dotenv";
import express from "express";
import multer from "multer";
import fetch from "node-fetch";
import FormData from "form-data";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

dotenv.config({ path: path.resolve("../../.env") });

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const upload = multer({ storage: multer.memoryStorage() });
const PYTHON_URL = process.env.PYTHON_SERVICE_URL || "http://localhost:8000";

app.use(cors());
app.use(express.json({ limit: "2mb" }));

async function proxyJson(method, url, body) {
  const response = await fetch(`${PYTHON_URL}${url}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

  const raw = await response.text();
  let data;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    const error = new Error(raw || "Upstream request failed");
    error.status = response.status;
    throw error;
  }

  if (!response.ok) {
    const error = new Error(data.detail || data.error || "Upstream request failed");
    error.status = response.status;
    throw error;
  }
  return data;
}

app.get("/health", async (_req, res) => {
  try {
    const pythonHealth = await fetch(`${PYTHON_URL}/api/health`).then((r) => r.json());
    res.json({ status: "ok", api: "node-gateway", python: pythonHealth });
  } catch (error) {
    res.status(503).json({ status: "degraded", error: error.message });
  }
});

app.post("/workspaces", async (req, res) => {
  try {
    const data = await proxyJson("POST", "/api/workspaces", req.body);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

app.get("/workspaces", async (_req, res) => {
  try {
    const data = await proxyJson("GET", "/api/workspaces");
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

app.get("/workspaces/:workspaceId/files", async (req, res) => {
  try {
    const data = await proxyJson("GET", `/api/workspaces/${req.params.workspaceId}/files`);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

app.get("/workspaces/:workspaceId/stats", async (req, res) => {
  try {
    const data = await proxyJson("GET", `/api/workspaces/${req.params.workspaceId}/stats`);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

app.post("/workspaces/:workspaceId/upload", upload.array("files"), async (req, res) => {
  try {
    const form = new FormData();
    for (const file of req.files || []) {
      form.append("files", file.buffer, {
        filename: file.originalname,
        contentType: file.mimetype,
      });
    }

    const response = await fetch(
      `${PYTHON_URL}/api/workspaces/${req.params.workspaceId}/upload`,
      {
        method: "POST",
        body: form,
        headers: form.getHeaders(),
      }
    );
    const data = await response.json();
    if (!response.ok) {
      return res.status(response.status).json(data);
    }
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post("/chat", async (req, res) => {
  try {
    const data = await proxyJson("POST", "/api/chat", req.body);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

app.post("/brd/generate", async (req, res) => {
  try {
    const data = await proxyJson("POST", "/api/brd/generate", req.body);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

app.get("/workspaces/:workspaceId/brd", async (req, res) => {
  try {
    const data = await proxyJson("GET", `/api/workspaces/${req.params.workspaceId}/brd`);
    res.json(data);
  } catch (error) {
    res.status(error.status || 500).json({ error: error.message });
  }
});

const port = process.env.API_PORT || 3001;
app.listen(port, () => {
  console.log(`API gateway listening on http://localhost:${port}`);
});
