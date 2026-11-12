import os
import re
import json
import io
import base64
import urllib.parse
import concurrent.futures
from PIL import Image
from pypdf import PdfReader
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

import google.generativeai as genai
from groq import Groq
from openai import OpenAI 

# 1. Load API Keys
load_dotenv()

# --- INISIALISASI AMAN (ANTI-CRASH DI RENDER) ---
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    genai.configure(api_key=gemini_key)

groq_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_key) if groq_key else None

def get_safe_openai_client(env_var_name, base_url):
    api_key = os.getenv(env_var_name)
    if not api_key:
        print(f"⚠️ Peringatan: {env_var_name} tidak ditemukan.")
        return None
    return OpenAI(api_key=api_key, base_url=base_url)

nvidia_client = get_safe_openai_client("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1")
openrouter_client = get_safe_openai_client("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1")
hf_client = get_safe_openai_client("HF_TOKEN", "https://router.huggingface.co/v1")
scaleway_client = get_safe_openai_client("SCALEWAY_API_KEY", "https://api.scaleway.ai/v1")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

SAVE_DIR = "generated_code"
HISTORY_FILE = "chat_history.json"
os.makedirs(SAVE_DIR, exist_ok=True)

# =====================================================================
# 🛡️ SECURITY PATCH: MEMATIKAN CODE RUNNER SEPENUHNYA
# =====================================================================
@app.post("/api/run_raw")
async def run_raw_code_disabled():
    # Menolak eksekusi kode dari publik dengan HTTP 403 Forbidden
    raise HTTPException(
        status_code=403, 
        detail="Fitur eksekusi kode dinonaktifkan di server publik demi keamanan."
    )

# =====================================================================
# FITUR LAINNYA TETAP BERJALAN NORMAL
# =====================================================================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f: return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/history")
async def get_history(): return {"history": load_history()}

@app.post("/api/clear")
async def clear_history():
    save_history([])
    return {"status": "cleared"}

def process_ai_response(text):
    pattern = r"\[SAVE_FILE:\s*(.*?)\]\s*```(?:\w+)?\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    saved_files = []
    for filename, code_content in matches:
        filepath = os.path.join(SAVE_DIR, filename.strip())
        try:
            with open(filepath, "w") as f: f.write(code_content)
            saved_files.append(filename.strip())
        except Exception as e: print(f"Gagal simpan: {e}")
            
    clean_text = re.sub(r"\[SAVE_FILE:\s*.*?\]\s*", "", text)
    if saved_files:
        return clean_text + f"\n\n✅ **(Sistem: File {', '.join(saved_files)} tersimpan!)**"
    return clean_text

@app.post("/api/chat")
async def chat_with_agent(
    message: str = Form(...), 
    model_choice: str = Form(...), 
    image: UploadFile = File(None),
    document: UploadFile = File(None)
):
    try:
        system_prompt = """Kamu adalah "Teman", AI Agent expert software engineering. 
        Gunakan bahasa Indonesia santai tapi profesional.
        
        [ATURAN MEMBUAT FILE]:
        Jika user meminta membuat file, balas dengan format:
        [SAVE_FILE: nama_file.py]
        ```python
        # kode di sini
        ```
        
        [ATURAN KODE INTERAKTIF]:
        JANGAN gunakan fungsi input(). Gunakan variabel statis atau argparse.
        
        [ATURAN PENTING - JANGAN BANYAK TANYA]:
        Jika user meminta script/kode, LANGSUNG BUATKAN KODENYA. Jangan balik bertanya.
        """

        history = load_history()
        
        doc_context = ""
        if document:
            if document.filename.endswith('.pdf'):
                pdf_reader = PdfReader(io.BytesIO(await document.read()))
                for page in pdf_reader.pages: doc_context += page.extract_text() + "\n"
            else:
                doc_context = (await document.read()).decode("utf-8", errors="ignore")
            doc_context = f"\n\n[KONTEKS DOKUMEN]:\n{doc_context[:5000]}" 
            history.append({"role": "user", "content": f"Baca dokumen ini: {document.filename}{doc_context}"})
        else:
            history.append({"role": "user", "content": message})

        if len(history) > 10: history = history[-10:]
        response_text = ""

        # MODE VISION
        if image:
            image_bytes = await image.read()
            try:
                if not gemini_key: raise Exception("Gemini API Key tidak ada.")
                img = Image.open(io.BytesIO(image_bytes))
                model = genai.GenerativeModel(model_name='gemini-2.5-flash', system_instruction=system_prompt)
                response = model.generate_content([message, img])
                response_text = f"🖼️ **Gemini Vision**\n\n{response.text}"
            except Exception:
                try:
                    if not openrouter_client: raise Exception("OpenRouter API Key tidak ada.")
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    fallback = openrouter_client.chat.completions.create(
                        model="qwen/qwen-2.5-vl-7b-instruct:free",
                        messages=[{"role": "user", "content": [{"type": "text", "text": message}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
                    )
                    response_text = f"🖼️ **Qwen Vision (Fallback)**\n\n{fallback.choices[0].message.content}"
                except Exception as e: response_text = f"Error Gambar: {str(e)}"

        # MODE BIKIN GAMBAR
        elif model_choice == "image_gen":
            try:
                if not groq_client: raise Exception("Groq API Key tidak ada.")
                enhancer = groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": "You are an expert prompt engineer."}, {"role": "user", "content": message}],
                    model="openai/gpt-oss-120b", temperature=0.7,
                )
                english_prompt = urllib.parse.quote(enhancer.choices[0].message.content)
                image_url = f"https://image.pollinations.ai/prompt/{english_prompt}?width=1024&height=1024&nologo=true"
                response_text = f"🎨 **Gambar Dibuat!**\n\n![Gambar]({image_url})"
            except Exception as e: response_text = f"Error: {str(e)}"

        # MODE SCRIPT VIDEO
        elif model_choice == "video_script":
            try:
                if not groq_client: raise Exception("Groq API Key tidak ada.")
                completion = groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": "Kamu Sutradara Film AI."}, {"role": "user", "content": message}],
                    model="openai/gpt-oss-120b", temperature=0.7,
                )
                response_text = f"🎬 **Script Video**\n\n{completion.choices[0].message.content}"
            except Exception as e: response_text = f"Error: {str(e)}"

        # MODE OMNI AI
        elif model_choice == "omni_ai":
            responses = {}
            
            def ask_gemini():
                if not gemini_key: return None
                try:
                    model = genai.GenerativeModel(model_name='gemini-2.5-flash', system_instruction=system_prompt)
                    gh = [{"role": "user" if msg["role"]=="user" else "model", "parts": [msg["content"]]} for msg in history]
                    return model.generate_content(gh).text
                except: return None

            def ask_groq():
                if not groq_client: return None
                try:
                    res = groq_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}] + history, model="openai/gpt-oss-120b")
                    return res.choices[0].message.content
                except: return None

            def ask_deepseek():
                if not nvidia_client: return None
                try:
                    res = nvidia_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model="deepseek-ai/deepseek-r1")
                    return res.choices[0].message.content
                except:
                    if not openrouter_client: return None
                    try:
                        fallback = openrouter_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model="meta-llama/llama-3-8b-instruct:free")
                        return fallback.choices[0].message.content
                    except: return None

            def ask_qwen():
                if not nvidia_client: return None
                try:
                    res = nvidia_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model="qwen/qwen2.5-coder-32b-instruct")
                    return res.choices[0].message.content
                except:
                    if not openrouter_client: return None
                    try:
                        fallback = openrouter_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model="mistralai/mistral-7b-instruct:free")
                        return fallback.choices[0].message.content
                    except: return None

            def ask_hf():
                if not hf_client: return None
                try:
                    res = hf_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model="meta-llama/Meta-Llama-3-8B-Instruct")
                    return res.choices[0].message.content
                except: return None

            def ask_scaleway():
                if not scaleway_client: return None
                try:
                    res = scaleway_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model="llama-3.3-70b-instruct")
                    return res.choices[0].message.content
                except: return None

            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    'Gemini': executor.submit(ask_gemini),
                    'Groq': executor.submit(ask_groq),
                    'DeepSeek': executor.submit(ask_deepseek),
                    'Qwen': executor.submit(ask_qwen),
                    'HuggingFace': executor.submit(ask_hf),
                    'Scaleway': executor.submit(ask_scaleway)
                }
                for name, future in futures.items():
                    try: responses[name] = future.result(timeout=40)
                    except: responses[name] = None

            valid_answers = {k: v for k, v in responses.items() if v}
            if not valid_answers:
                response_text = "Waduh, semua AI sedang limit atau API Key belum dimasukkan."
            else:
                synth_prompt = f"Rangkum jawaban coding terbaik dari AI berikut:\n\n"
                for name, ans in valid_answers.items(): synth_prompt += f"--- {name} ---\n{ans}\n\n"
                try:
                    if groq_client:
                        final_res = groq_client.chat.completions.create(messages=[{"role": "user", "content": synth_prompt}], model="openai/gpt-oss-120b", temperature=0.3)
                        summary = final_res.choices[0].message.content
                    else:
                        summary = list(valid_answers.values())[0]
                    response_text = f"🤖 **Omni AI Council**\n*(Hadir: {', '.join(valid_answers.keys())})*\n\n{summary}"
                except:
                    response_text = f"🤖 **Omni AI**\n\n{list(valid_answers.values())[0]}"

        history.append({"role": "assistant", "content": response_text})
        save_history(history)
        return {"reply": process_ai_response(response_text)}

    except Exception as e:
        return {"error": str(e)}
