"""
FastAPI Server Runner
ใช้ script นี้เมื่อ --reload ของ uvicorn ไม่ทำงานถูกต้อง

วิธีใช้:
1. Stop server เดิม (กด 🟥 หรือ Ctrl+C)
2. Run ใหม่ (กด ▶️ หรือ F5)
"""
import uvicorn
import sys
import importlib

# Clear module cache สำหรับ app modules
modules_to_clear = [mod for mod in sys.modules.keys() if mod.startswith('app.')]
for mod in modules_to_clear:
    del sys.modules[mod]

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting FastAPI Server...")
    print("💡 Tip: กด Ctrl+C แล้ว F5 เพื่อ restart")
    print("=" * 60)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8201,
        reload=True,
        reload_dirs=["app"],
    )

