from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
import uvicorn
import pypdf
import io

 
from policy_checker import PROJECT_ROOT

app = FastAPI(title="PolicyChecker Compliance Dashboard", version="2.0.0")


# ── Data paths ────────────────────────────────────────────────────────────
POLICY_DIR = PROJECT_ROOT / "data" / "institutional_policy" / "ait"

def find_policy():
    pdf_files = list(POLICY_DIR.glob("*.pdf"))
    if pdf_files:
        return pdf_files[0]
    return None

@app.get("/api/policy")
async def get_policy():
    policy_file = find_policy()
    if not policy_file:
        raise HTTPException(status_code=404, detail="No policy PDF found")
    return str(policy_file)

@app.post("/api/policy")
async def upload_policy(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Uploaded file is not a valid PDF")
    try:
        reader = pypdf.PdfReader(io.BytesIO(contents))
        _ = len(reader.pages)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF is corrupted or unreadable: {e}")
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    policy_file = find_policy()
    if policy_file:
        policy_file.unlink()
    new_policy_file = POLICY_DIR / file.filename
    new_policy_file.write_bytes(contents)
    return {"message": "Policy PDF uploaded successfully", "path": str(new_policy_file)}

@app.delete("/api/policy")
async def delete_policy():
    policy_file = find_policy()
    if policy_file:
        policy_file.unlink()
    return {"message": "Policy PDF removed successfully"}

def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
