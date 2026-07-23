const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

export async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.detail || "Request failed");
  }
  return data;
}

export async function createWorkspace(name = "BRD Workspace") {
  return api("/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function uploadFiles(workspaceId, files) {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const response = await fetch(`${API_BASE}/workspaces/${workspaceId}/upload`, {
    method: "POST",
    body: form,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.detail || "Upload failed");
  }
  return data;
}

export async function listFiles(workspaceId) {
  return api(`/workspaces/${workspaceId}/files`);
}

export async function getStats(workspaceId) {
  return api(`/workspaces/${workspaceId}/stats`);
}

export async function sendChat(payload) {
  return api("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function generateBrd(workspaceId, title) {
  return api("/brd/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId, title }),
  });
}

export async function listBrdDocuments(workspaceId) {
  return api(`/workspaces/${workspaceId}/brd`);
}
