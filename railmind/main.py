from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uuid
from datetime import datetime

from railmind.api.routes import set_agent
from railmind.agent.react_agent import ReActAgent
from railmind.function_call.kg_tools import kg_system
from railmind.operators.logger import get_logger
from railmind.api.routes import router, set_agent
from railmind.config import get_settings

agent: ReActAgent = None
logger = get_logger(name="RailMind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global agent
    logger.info("Initializing ReAct Agent...")
    agent = ReActAgent()
    set_agent(agent)
    logger.info("ReAct Agent Initialization Complete")
    yield # The code before `yield` will execute when `main.py` starts; the code after `main.py` will execute when `main.py` closes.
    logger.info("🔌Closing Database Connection...")
    kg_system.close()
    logger.info("👋The Application is Closed.")



def create_app() -> FastAPI:
    app = FastAPI(
        title="RailMind-12306 Agent",
        description="基于LangGraph12306铁路智能问答Agent系统",
        version="0.1.0",
        lifespan=lifespan
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    @app.get("/")
    async def root():
        return {
            "message": "ReAct KG Agent API",
            "version": "0.1.0",
            "status": "running"
        }
    
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat()
        }
    
    return app
app = create_app()
if __name__ == "__main__":
    import uvicorn
    # uvicorn railmind.main:app --reload
    settings = get_settings()
    
    logger.info("✨" * 30)
    logger.info("                      🚄 RailMind 12306")
    logger.info("✨" * 30)
    
    uvicorn.run(
        app,
        host=settings.backend_host,
        port=settings.backend_port,
        log_level="info"
    )
