# 🦅 Teman AI Ultimate Coding Agent

Sebuah platform AI Agent multifungsi yang menggabungkan kekuatan 6 model AI raksasa untuk membantu proses *coding*, analisis gambar, pembuatan gambar, hingga pembuatan *script* video. Dilengkapi dengan fitur *Voice Assistant* (bicara dan didengar) serta eksekusi kode langsung dari browser.

## ✨ Fitur Utama

- **🤖 Omni AI Council:** Musyawarah gabungan dari 6 model AI raksasa (Gemini, Groq, DeepSeek, Qwen, Hugging Face, Scaleway) untuk memberikan jawaban coding terbaik.
- **🎙️ Voice Assistant (Speech-to-Text & TTS):** Berbicara langsung ke AI dan biarkan AI membacakan jawabannya (didukung oleh Web Speech API).
- **🖼️ Vision (Analisis Gambar):** Unggah *screenshot* error atau desain UI, dan AI akan menganalisisnya (didukung oleh Gemini Vision & Qwen VL).
- **📄 Document Upload (RAG Lite):** Unggah dokumen `.txt`, `.py`, atau `.pdf` dan tanyakan isinya ke AI.
- **🎨 Generative Image:** Membuat gambar dari teks (didukung oleh Pollinations AI).
- **🎬 Video Script Director:** Membuat *storyboard* dan *prompt* video profesional siap pakai untuk CapCut/Kling AI.
- **▶️ Code Runner:** Menjalankan kode Python langsung dari antarmuka web dan melihat *output*-nya secara *real-time*.
- **💾 Auto-Save Code:** AI dapat menyimpan kode yang dibuatnya langsung ke dalam folder laptop/server.
- **🧠 Persistent Memory:** AI mengingat percakapan sebelumnya meskipun halaman di-*refresh*.

## 🛠️ Tech Stack

- **Backend:** Python, FastAPI, Uvicorn
- **Frontend:** HTML, CSS, Vanilla JavaScript, Highlight.js, Marked.js, Chart.js
- **AI Providers:** Google Gemini, Groq, NVIDIA NIM, OpenRouter, Hugging Face, Scaleway, Pollinations AI.

## 🚀 Cara Menjalankan Secara Lokal

1. **Clone Repository**
   ```bash
   git clone https://github.com/ramdanmakhdum-dev/coding-agent.git
   cd coding-agent
