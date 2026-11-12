import os
import re
import json
import subprocess
import sys
import io
import base64
import urllib.parse
import concurrent.futures
from PIL import Image
from pypdf import PdfReader
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

import google.generativeai as genai
from groq import Groq
from openai import OpenAI 

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

nvidia_client = OpenAI(api_key=os.getenv("NVIDIA_API_KEY"), base_url="https://integrate.api.nvidia.com/v1")
openrouter_client = OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1")
hf_client = OpenAI(api_key=os.getenv("HF_TOKEN"), base_url="https://router.huggingface.co/v1")

app = FastAPI()
templates = Jinja2Templates(directory="templates")
SAVE_DIR = "generated_code"
HISTORY_FILE = "chat_history.json"
os.makedirs(SAVE_DIR, exist_ok=True)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f: return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history, f)

class RawCodeRequest(BaseModel):
    code: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/history")
async def get_history(): return {"history": load_history()}

@app.post("/api/clear")
async def clear_history():
    save_history([])
    return {"status": "cleared"}

@app.post("/api/run_raw")
async def run_raw_code(request: RawCodeRequest):
    temp_file = os.path.join(SAVE_DIR, "temp_execution.py")
    try:
        with open(temp_file, "w") as f: f.write(request.code)
        result = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=5)
        output = result.stdout + ("\n" + result.stderr if result.stderr else "")
        if os.path.exists(temp_file): os.remove(temp_file)
        return {"output": output.strip() or "(Kode berjalan sukses, tanpa output.)"}
    except subprocess.TimeoutExpired:
        if os.path.exists(temp_file): os.remove(temp_file)
        return {"error": "Waktu habis (lebih dari 5 detik)."}
    except Exception as e:
        if os.path.exists(temp_file): os.remove(temp_file)
        return {"error": str(e)}

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
    document: UploadFile = File(None) # Fitur Dokumen (RAG)
):
    try:
        system_prompt = """Kamu adalah "Teman", AI Agent expert software engineering. 
        Gunakan bahasa Indonesia santai tapi profesional.
        Jika user meminta membuat file, balas: [SAVE_FILE: nama_file.py] lalu ```python ... ```
        JANGAN gunakan input() pada kode yang dibuat."""

        history = load_history()
        
        # --- LOGIKA BACA DOKUMEN (RAG LITE) ---
        doc_context = ""
        if document:
            if document.filename.endswith('.pdf'):
                pdf_reader = PdfReader(io.BytesIO(await document.read()))
                for page in pdf_reader.pages:
                    doc_context += page.extract_text() + "\n"
            else:
                doc_context = (await document.read()).decode("utf-8", errors="ignore")
            doc_context = f"\n\n[KONTEKS DOKUMEN YANG DIUPLOAD]:\n{doc_context[:5000]}" # Batasi 5000 char agar tidak error
            
            history.append({"role": "user", "content": f"Baca dokumen ini: {document.filename}{doc_context}"})
        else:
            history.append({"role": "user", "content": message})

        if len(history) > 10: history = history[-10:]
        response_text = ""

        # 1. MODE VISION (GAMBAR)
        if image:
            image_bytes = await image.read()
            try:
                img = Image.open(io.BytesIO(image_bytes))
                model = genai.GenerativeModel(model_name='gemini-2.5-flash', system_instruction=system_prompt)
                response = model.generate_content([message, img])
                response_text = f"🖼️ **Gemini Vision**\n\n{response.text}"
            except Exception:
                try:
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    fallback = openrouter_client.chat.completions.create(
                        model="qwen/qwen-2.5-vl-7b-instruct:free",
                        messages=[{"role": "user", "content": [{"type": "text", "text": message}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
                    )
                    response_text = f"🖼️ **Qwen Vision**\n\n{fallback.choices[0].message.content}"
                except Exception as e: response_text = f"Error Gambar: {str(e)}"

        # 2. MODE BIKIN GAMBAR
        elif model_choice == "image_gen":
            try:
                enhancer = groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": "You are an expert prompt engineer. Translate to English prompt."}, {"role": "user", "content": message}],
                    model="openai/gpt-oss-120b", temperature=0.7,
                )
                english_prompt = urllib.parse.quote(enhancer.choices[0].message.content)
                image_url = f"https://image.pollinations.ai/prompt/{english_prompt}?width=1024&height=1024&nologo=true"
                response_text = f"🎨 **Gambar Dibuat!**\n\n![Gambar]({image_url})"
            except Exception as e: response_text = f"Error: {str(e)}"

        # 3. MODE SCRIPT VIDEO
        elif model_choice == "video_script":
            try:
                completion = groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": "Kamu Sutradara Film AI. Buat storyboard 10-15 detik."}, {"role": "user", "content": message}],
                    model="openai/gpt-oss-120b", temperature=0.7,
                )
                response_text = f"🎬 **Script Video**\n\n{completion.choices[0].message.content}"
            except Exception as e: response_text = f"Error: {str(e)}"

        # 4. MODE OMNI AI (MUSYAWARAH MODEL)
        elif model_choice == "omni_ai":
            responses = {}
            def ask_gemini():
                try:
                    model = genai.GenerativeModel(model_name='gemini-2.5-flash', system_instruction=system_prompt)
                    gh = [{"role": "user" if msg["role"]=="user" else "model", "parts": [msg["content"]]} for msg in history]
                    return model.generate_content(gh).text
                except: return None

            def ask_groq():
                try:
                    res = groq_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}] + history, model="openai/gpt-oss-120b")
                    return res.choices[0].message.content
                except: return None

            def ask_nvidia(model_name):
                try:
                    res = nvidia_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model=model_name)
                    return res.choices[0].message.content
                except: return None

            def ask_hf():
                try:
                    res = hf_client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}], model="meta-llama/Meta-Llama-3-8B-Instruct")
                    return res.choices[0].message.content
                except: return None

            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    'Gemini': executor.submit(ask_gemini),
                    'Groq': executor.submit(ask_groq),
                    'DeepSeek': executor.submit(ask_nvidia, "deepseek-ai/deepseek-r1"),
                    'Qwen': executor.submit(ask_nvidia, "qwen/qwen2.5-coder-32b-instruct"),
                    'HuggingFace': executor.submit(ask_hf)
                }
                for name, future in futures.items():
                    try: responses[name] = future.result(timeout=40)
                    except: responses[name] = None

            valid_answers = {k: v for k, v in responses.items() if v}
            if not valid_answers:
                response_text = "Waduh, semua AI sedang limit. Coba lagi nanti."
            else:
                synth_prompt = f"Rangkum jawaban coding terbaik dari AI berikut:\n\n"
                for name, ans in valid_answers.items(): synth_prompt += f"--- {name} ---\n{ans}\n\n"
                try:
                    final_res = groq_client.chat.completions.create(messages=[{"role": "user", "content": synth_prompt}], model="openai/gpt-oss-120b", temperature=0.3)
                    summary = final_res.choices[0].message.content
                    response_text = f"🤖 **Omni AI Council**\n*(Hadir: {', '.join(valid_answers.keys())})*\n\n{summary}"
                except:
                    response_text = f"🤖 **Omni AI**\n\n{list(valid_answers.values())[0]}"

        history.append({"role": "assistant", "content": response_text})
        save_history(history)
        return {"reply": process_ai_response(response_text)}

    except Exception as e:
        return {"error": str(e)}
