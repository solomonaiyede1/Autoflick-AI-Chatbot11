
import axios from "axios";

const API = axios.create({
  baseURL: "https://autoflick-ai-chatbot11-backend.onrender.com",
  headers: {
    "Content-Type": "application/json",
  },
});

export const sendMessage = async (message) => {
  try {
    const response = await API.post("https://autoflick-ai-chatbot11-backend.onrender.com/api/chat", {
      message,
    });

    return response.data;
  } catch (error) {
    console.error("Chat API error:", error);
    throw error;
  }
};

export default API;
