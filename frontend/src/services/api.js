
const API_URL = "https://autoflick-ai-chatbot11-backend.onrender.com";

// NORMAL AI CHAT
export async function sendMessage(messages, conversationId = null) {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      messages,
      conversation_id: conversationId,
    }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.error || "Autoflick AI could not process your request."
    );
  }

  return data;
}

// PDF DOCUMENT ANALYSIS
export async function analyzeDocument(
  file,
  question = "",
  conversationId = null
) {
  const formData = new FormData();

  formData.append("file", file);
  formData.append("question", question);

  if (conversationId !== null) {
    formData.append("conversation_id", conversationId);
  }

  const response = await fetch(`${API_URL}/api/analyze-document`, {
    method: "POST",
    body: formData,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.error || "Autoflick AI could not analyse your document."
    );
  }

  return data;
}

// GET ALL CONVERSATIONS
export async function getConversations() {
  const response = await fetch(`${API_URL}/api/conversations`);

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || "Unable to load conversations.");
  }

  return data.conversations;
}

// GET ONE CONVERSATION
export async function getConversation(conversationId) {
  const response = await fetch(
    `${API_URL}/api/conversations/${conversationId}`
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || "Unable to load this conversation.");
  }

  return data;
}

// DELETE CONVERSATION
export async function deleteConversation(conversationId) {
  const response = await fetch(
    `${API_URL}/api/conversations/${conversationId}`,
    {
      method: "DELETE",
    }
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || "Unable to delete conversation.");
  }

  return data;
}
