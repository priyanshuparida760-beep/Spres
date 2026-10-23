#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║              AXIOM'S TELEGRAM-BACKED WHATSAPP SPAMMER BOT v4.0                ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  • Premium Telegram interface with admin controls                            ║
║  • Credit system (2 per successful send, 0 for failed)                       ║
║  • Direct APK upload and distribution                                        ║
║  • Vehicle RC scanning with real API                                         ║
║  • Persistent user management with pickle DB                                 ║
║  • WhatsApp authentication with QR code per user                             ║
║  • Professional preset messages (5 templates)                                ║
║  • No filters - send to all numbers found                                    ║
║  • Multi-session WhatsApp support                                            ║
║  • Automatic retry on failed sends                                           ║
║  • Rate limiting and anti-ban delays                                         ║
║  • Full campaign analytics and reporting                                     ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
import sys
import json
import re
import random
import logging
import queue
import hashlib
import time
import threading
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict, field
import pickle
import shutil
import traceback
from collections import defaultdict

# Third party imports
import aiohttp
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputFile, BufferedInputFile,
    ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, Message, User as TgUser,
    Chat, ChatMember, ChatMemberUpdated
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.enums import ParseMode, ChatType, ChatMemberStatus
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, 
    TelegramRetryAfter, TelegramNetworkError
)

from playwright.async_api import async_playwright, Playwright, BrowserContext, Page, Error as PlaywrightError
import qrcode
from PIL import Image
import subprocess

# ============================================================================
# CONFIGURATION SECTION
# ============================================================================

BOT_TOKEN = "8554379476:AAHZf4qPgmiCQ5rOQCgovwJX88hSjJPf3iQ"
SUPER_ADMIN_ID = 8855682217
RC_API_URL = "https://rc-info-1api.onrender.com/api/vehicle-info?rc=rc_number"
USER_DATA_DIR = "./whatsapp_user_data"
APK_STORAGE_DIR = "./apk_storage"
DATABASE_FILE = "./axiom_bot_db.pkl"
LOG_FILE = "./axiom_bot.log"
QR_IMAGE_PATH = "whatsapp_qr.png"
BOT_VERSION = "4.0"
BOT_NAME = "AXIOM SPREADER"

# Rate limiting settings
MESSAGE_DELAY_MIN = 8      # Minimum seconds between messages
MESSAGE_DELAY_MAX = 15     # Maximum seconds between messages
SCAN_DELAY_MIN = 0.3       # Minimum seconds between API calls
SCAN_DELAY_MAX = 0.8       # Maximum seconds between API calls
MAX_RETRIES = 3            # Maximum retries for failed sends
WHATSAPP_TIMEOUT = 30000   # Timeout for WhatsApp operations

# Credit settings
CREDITS_PER_SUCCESS = 2     # Credits deducted per successful send
INITIAL_CREDITS = 10        # Initial credits for new users
MAX_TASK_COUNT = 500        # Maximum vehicles per scan task

# ============================================================================
# PROFESSIONAL PRESET MESSAGES
# ============================================================================

PRESET_MESSAGES = [
    """🚨 *RTO CHALLAN NOTICE* 🚨

*Vehicle:* `{rc_number}`
*Owner:* {owner_name}
*Status:* {insurance_status}

⚠️ Your vehicle has a pending challan.
💰 *Pay just ₹1* to clear the fine immediately!

🔗 *Download App:* {apk_link}

_Valid for 24 hours only._""",

    """📢 *TRAFFIC VIOLATION ALERT* 📢

`{rc_number}` | {owner_name}

A traffic challan has been issued against your vehicle.

⚡ *Settle for ₹1 - Limited Period Offer* ⚡

📱 *Click:* {apk_link}

_This is an official RTO notification._""",

    """⚠️ *FINAL CHALLAN REMINDER* ⚠️

*Vehicle:* `{rc_number}`
*Owner:* {owner_name}

🚨 Your vehicle is flagged for pending challan.

💎 *Pay just ₹1 through our official app* 💎

👉 {apk_link}

_Act now to avoid legal action._""",

    """🔴 *RTO ENFORCEMENT NOTICE* 🔴

*To:* {owner_name} (`{rc_number}`)

*Insurance Status:* {insurance_status}

Your vehicle has been marked for pending traffic violations.

✅ *Clear challan in 1 Rupee* ✅

📲 {apk_link}

_This notice will expire in 48 hours._""",

    """💰 *CHALLAN SETTLEMENT OFFER* 💰

*Vehicle:* `{rc_number}`
*Owner:* {owner_name}

🎯 *Get 99% discount on your pending challan!*

🔥 *Pay only ₹1 via RTO Challan App* 🔥

👉 {apk_link}

_Hurry! Limited time offer._"""
]

# ============================================================================
# LOGGING SETUP
# ============================================================================

class CustomFormatter(logging.Formatter):
    """Custom log formatter with colors"""
    
    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    green = "\x1b[32;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    
    FORMATS = {
        logging.DEBUG: grey + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.INFO: green + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.WARNING: yellow + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.ERROR: red + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.CRITICAL: bold_red + "%(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

# Setup file handler
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Setup console handler with colors
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(CustomFormatter())

# Configure root logger
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE MODELS
# ============================================================================

@dataclass
class User:
    """User data model"""
    user_id: int
    username: str = ""
    first_name: str = ""
    credits: int = INITIAL_CREDITS
    is_admin: bool = False
    is_super_admin: bool = False
    is_active: bool = True
    join_date: datetime = field(default_factory=datetime.now)
    total_sent: int = 0
    total_failed: int = 0
    last_active: datetime = field(default_factory=datetime.now)
    apk_file_id: str = ""
    custom_message: str = ""
    whatsapp_authenticated: bool = False
    total_tasks: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'credits': self.credits,
            'is_admin': self.is_admin,
            'is_super_admin': self.is_super_admin,
            'is_active': self.is_active,
            'join_date': self.join_date.isoformat() if self.join_date else None,
            'total_sent': self.total_sent,
            'total_failed': self.total_failed,
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'apk_file_id': self.apk_file_id,
            'custom_message': self.custom_message,
            'whatsapp_authenticated': self.whatsapp_authenticated,
            'total_tasks': self.total_tasks
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create from dictionary"""
        if data.get('join_date'):
            data['join_date'] = datetime.fromisoformat(data['join_date'])
        if data.get('last_active'):
            data['last_active'] = datetime.fromisoformat(data['last_active'])
        return cls(**data)

@dataclass
class Task:
    """Task data model"""
    task_id: str
    user_id: int
    rc_start: str
    count: int
    status: str = "pending"
    targets_found: int = 0
    messages_sent: int = 0
    messages_failed: int = 0
    credits_used: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime = None
    completed_at: datetime = None
    result_file: str = ""
    error_message: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'rc_start': self.rc_start,
            'count': self.count,
            'status': self.status,
            'targets_found': self.targets_found,
            'messages_sent': self.messages_sent,
            'messages_failed': self.messages_failed,
            'credits_used': self.credits_used,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result_file': self.result_file,
            'error_message': self.error_message
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """Create from dictionary"""
        for time_field in ['created_at', 'started_at', 'completed_at']:
            if data.get(time_field):
                data[time_field] = datetime.fromisoformat(data[time_field])
        return cls(**data)

@dataclass
class WhatsAppSession:
    """WhatsApp session data model"""
    session_id: str
    user_id: int
    is_active: bool = False
    last_used: datetime = field(default_factory=datetime.now)
    auth_method: str = ""
    failed_attempts: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'is_active': self.is_active,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'auth_method': self.auth_method,
            'failed_attempts': self.failed_attempts
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WhatsAppSession':
        """Create from dictionary"""
        if data.get('last_used'):
            data['last_used'] = datetime.fromisoformat(data['last_used'])
        return cls(**data)

# ============================================================================
# DATABASE MANAGER
# ============================================================================

class Database:
    """Persistent database manager using pickle"""
    
    def __init__(self):
        self.users: Dict[int, User] = {}
        self.tasks: Dict[str, Task] = {}
        self.sessions: Dict[str, WhatsAppSession] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.lock = asyncio.Lock()
        self.load()
    
    def load(self):
        """Load database from pickle file"""
        try:
            if os.path.exists(DATABASE_FILE):
                with open(DATABASE_FILE, 'rb') as f:
                    data = pickle.load(f)
                    
                    # Load users
                    for user_id, user_data in data.get('users', {}).items():
                        self.users[int(user_id)] = User.from_dict(user_data)
                    
                    # Load tasks
                    for task_id, task_data in data.get('tasks', {}).items():
                        self.tasks[task_id] = Task.from_dict(task_data)
                    
                    # Load sessions
                    for session_id, session_data in data.get('sessions', {}).items():
                        self.sessions[session_id] = WhatsAppSession.from_dict(session_data)
                    
                    logger.info(f"✅ Loaded {len(self.users)} users, {len(self.tasks)} tasks, {len(self.sessions)} sessions")
            else:
                self._initialize_defaults()
                
        except Exception as e:
            logger.error(f"❌ Failed to load database: {e}")
            self._initialize_defaults()
    
    def _initialize_defaults(self):
        """Initialize database with default data"""
        super_admin = User(
            user_id=SUPER_ADMIN_ID,
            username="SuperAdmin",
            first_name="Super Admin",
            credits=999999,
            is_admin=True,
            is_super_admin=True
        )
        self.users[SUPER_ADMIN_ID] = super_admin
        self.save()
        logger.info("✅ Database initialized with super admin")
    
    def save(self):
        """Save database to pickle file"""
        try:
            users_data = {user_id: user.to_dict() for user_id, user in self.users.items()}
            tasks_data = {task_id: task.to_dict() for task_id, task in self.tasks.items()}
            sessions_data = {session_id: session.to_dict() for session_id, session in self.sessions.items()}
            
            data = {
                'users': users_data,
                'tasks': tasks_data,
                'sessions': sessions_data
            }
            
            with open(DATABASE_FILE, 'wb') as f:
                pickle.dump(data, f)
                
            logger.debug("✅ Database saved")
            
        except Exception as e:
            logger.error(f"❌ Failed to save database: {e}")
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return self.users.get(user_id)
    
    def add_user(self, user_id: int, username: str = "", first_name: str = "") -> User:
        """Add new user or return existing"""
        if user_id not in self.users:
            user = User(
                user_id=user_id,
                username=username or f"user_{user_id}",
                first_name=first_name or f"User {user_id}"
            )
            self.users[user_id] = user
            self.save()
            logger.info(f"✅ New user added: {user_id} (@{username})")
        else:
            user = self.users[user_id]
            user.last_active = datetime.now()
            if username and user.username != username:
                user.username = username
                self.save()
        
        return self.users[user_id]
    
    def update_user_credits(self, user_id: int, amount: int) -> bool:
        """Update user credits"""
        user = self.get_user(user_id)
        if user:
            user.credits += amount
            if user.credits < 0:
                user.credits = 0
            self.save()
            return True
        return False
    
    def deduct_credits_for_send(self, user_id: int, success: bool) -> bool:
        """Deduct credits for message send"""
        if success:
            return self.update_user_credits(user_id, -CREDITS_PER_SUCCESS)
        return True  # No deduction for failed sends
    
    def create_task(self, user_id: int, rc_start: str, count: int) -> Task:
        """Create new scanning task"""
        task_id = f"task_{user_id}_{int(time.time())}_{random.randint(1000, 9999)}"
        task = Task(
            task_id=task_id,
            user_id=user_id,
            rc_start=rc_start,
            count=count
        )
        self.tasks[task_id] = task
        
        # Update user total tasks
        user = self.get_user(user_id)
        if user:
            user.total_tasks += 1
        
        self.save()
        logger.info(f"✅ Task created: {task_id}")
        return task
    
    def update_task_status(self, task_id: str, status: str, **kwargs):
        """Update task status and optional fields"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = status
            
            if status == "sending" and not task.started_at:
                task.started_at = datetime.now()
            elif status in ["completed", "failed", "cancelled"]:
                task.completed_at = datetime.now()
            
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            
            self.save()
            logger.info(f"✅ Task {task_id} status updated to {status}")
    
    def get_user_tasks(self, user_id: int, limit: int = 10) -> List[Task]:
        """Get tasks for a user"""
        user_tasks = [task for task in self.tasks.values() if task.user_id == user_id]
        user_tasks.sort(key=lambda t: t.created_at, reverse=True)
        return user_tasks[:limit]
    
    def get_all_tasks(self, limit: int = 50) -> List[Task]:
        """Get all tasks"""
        tasks = list(self.tasks.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]
    
    def set_user_admin(self, user_id: int, is_admin: bool) -> bool:
        """Set user admin status"""
        user = self.get_user(user_id)
        if user:
            user.is_admin = is_admin
            self.save()
            logger.info(f"✅ User {user_id} admin status: {is_admin}")
            return True
        return False
    
    def get_all_users(self) -> List[User]:
        """Get all users"""
        return list(self.users.values())
    
    def save_user_apk(self, user_id: int, apk_file_id: str) -> bool:
        """Save user's APK file ID"""
        user = self.get_user(user_id)
        if user:
            user.apk_file_id = apk_file_id
            self.save()
            logger.info(f"✅ APK saved for user {user_id}")
            return True
        return False
    
    def save_user_message(self, user_id: int, custom_message: str) -> bool:
        """Save user's custom message"""
        user = self.get_user(user_id)
        if user:
            user.custom_message = custom_message
            self.save()
            return True
        return False
    
    def set_whatsapp_auth_status(self, user_id: int, authenticated: bool) -> bool:
        """Set WhatsApp authentication status"""
        user = self.get_user(user_id)
        if user:
            user.whatsapp_authenticated = authenticated
            self.save()
            return True
        return False
    
    def get_stats(self) -> dict:
        """Get database statistics"""
        total_credits = sum(u.credits for u in self.users.values())
        total_sent = sum(u.total_sent for u in self.users.values())
        total_failed = sum(u.total_failed for u in self.users.values())
        
        return {
            'total_users': len(self.users),
            'total_admins': sum(1 for u in self.users.values() if u.is_admin),
            'total_credits': total_credits,
            'total_sent': total_sent,
            'total_failed': total_failed,
            'total_tasks': len(self.tasks)
        }

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_vehicle_range(start_rc: str, count: int) -> List[str]:
    """Parse vehicle number and generate range"""
    # Support multiple formats: MH12AB1234, MH-12-AB-1234, MH12 AB 1234
    start_rc = re.sub(r'[\s\-]', '', start_rc).upper()
    
    # Try to match pattern: 2 letters + 2 digits + 2 letters + numbers
    match = re.match(r'([A-Z]{2})(\d{2})([A-Z]{2})(\d+)', start_rc)
    if not match:
        # Try alternative: 2 letters + 2 digits + numbers (no letters in middle)
        match = re.match(r'([A-Z]{2})(\d{2})(\d+)', start_rc)
        if match:
            prefix = f"{match.group(1)}{match.group(2)}"
            start_num = int(match.group(3))
            num_length = max(4, len(match.group(3)))
            return [f"{prefix}{str(start_num + i).zfill(num_length)}" for i in range(count)]
        raise ValueError(f"Invalid RC format: {start_rc}")
    
    prefix = f"{match.group(1)}{match.group(2)}{match.group(3)}"
    start_num = int(match.group(4))
    num_length = max(4, len(match.group(4)))
    
    return [f"{prefix}{str(start_num + i).zfill(num_length)}" for i in range(count)]

async def fetch_vehicle_info(rc_number: str, retry: int = 2) -> Optional[Dict]:
    """Fetch vehicle info from RC API with retry"""
    for attempt in range(retry + 1):
        try:
            url = RC_API_URL.format(rc_number=rc_number)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    elif response.status == 429:  # Rate limited
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        break
        except Exception as e:
            if attempt == retry:
                logger.debug(f"API error for {rc_number}: {e}")
            else:
                await asyncio.sleep(1)
    
    return None

def extract_phone_from_vehicle(vehicle_data: Dict) -> Optional[str]:
    """Extract phone number from vehicle data"""
    # Try multiple possible fields
    basic_info = vehicle_data.get("basic_info", {})
    
    phone = basic_info.get("phone", "")
    if phone and phone != "Not Available" and phone != "NA":
        phone = re.sub(r'[^0-9+]', '', phone)
        if len(phone) == 10:
            phone = f"+91{phone}"
        elif len(phone) > 10 and not phone.startswith('+'):
            phone = f"+{phone}"
        return phone
    
    # Try other possible fields
    owner_details = vehicle_data.get("owner_details", {})
    phone = owner_details.get("phone", "")
    if phone and phone != "Not Available" and phone != "NA":
        phone = re.sub(r'[^0-9+]', '', phone)
        if len(phone) == 10:
            phone = f"+91{phone}"
        elif len(phone) > 10 and not phone.startswith('+'):
            phone = f"+{phone}"
        return phone
    
    return None

def extract_name_from_vehicle(vehicle_data: Dict) -> str:
    """Extract owner name from vehicle data"""
    basic_info = vehicle_data.get("basic_info", {})
    name = basic_info.get("owner_name", "")
    
    if name and name != "Not Available":
        # Remove asterisks and clean up
        name = re.sub(r'[*]+', '', name).strip()
        return name
    
    # Try other fields
    owner_details = vehicle_data.get("owner_details", {})
    name = owner_details.get("owner_name", "")
    if name and name != "Not Available":
        name = re.sub(r'[*]+', '', name).strip()
        return name
    
    return "Vehicle Owner"

def extract_insurance_status(vehicle_data: Dict) -> str:
    """Extract insurance status from vehicle data"""
    insurance = vehicle_data.get("insurance", {})
    status = insurance.get("status", "")
    
    if status:
        if "Expired" in status:
            expired_days = insurance.get("expired_days_ago", 0)
            return f"Expired ({expired_days} days ago)"
        return status
    
    validity = vehicle_data.get("validity", {})
    insurance_upto = validity.get("insurance_upto", "")
    if insurance_upto and insurance_upto != "NA":
        return f"Valid until {insurance_upto}"
    
    return "Unknown"

def generate_progress_bar(current: int, total: int, width: int = 20) -> str:
    """Generate progress bar string"""
    if total == 0:
        return "[░░░░░░░░░░░░░░░░░░░░] 0%"
    
    progress = int((current / total) * width)
    bar = "█" * progress + "░" * (width - progress)
    percentage = (current / total * 100)
    return f"[{bar}] {percentage:.1f}% ({current}/{total})"

def format_credits(credits: int) -> str:
    """Format credits with emoji"""
    if credits >= 100000:
        return f"💎 {credits:,} CREDITS"
    elif credits >= 10000:
        return f"💰 {credits:,} CREDITS"
    elif credits >= 1000:
        return f"💳 {credits:,} CREDITS"
    else:
        return f"🪙 {credits:,} CREDITS"

def format_time(seconds: int) -> str:
    """Format time duration"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

# ============================================================================
# WHATSAPP MANAGER
# ============================================================================

class WhatsAppManager:
    """Manages WhatsApp Web automation with per-user sessions (HEADLESS MODE FOR VPS)"""
    
    def __init__(self, db: Database):
        self.db = db
        self.playwright: Optional[Playwright] = None
        self.browser_context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_authenticated = False
        self.current_user_id: Optional[int] = None
        self.bot: Optional[Bot] = None
        self._auth_tasks: Dict[int, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        logger.info("✅ WhatsApp Manager initialized")
    
    async def initialize(self):
        """Initialize WhatsApp manager"""
        try:
            # Install playwright dependencies automatically
            logger.info("Installing Playwright browsers and dependencies if missing...")
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                if sys.platform.startswith("linux"):
                    subprocess.run([sys.executable, "-m", "playwright", "install-deps", "chromium"], check=False)
            except Exception as deps_e:
                logger.warning(f"Failed to auto-install dependencies: {deps_e}")
                
            self.playwright = await async_playwright().start()
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            os.makedirs(APK_STORAGE_DIR, exist_ok=True)
            logger.info("✅ WhatsApp manager ready")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WhatsApp manager: {e}")
            raise
    
    async def generate_qr_for_user(self, user_id: int) -> Optional[str]:
        """Generate WhatsApp QR code for a specific user"""
        async with self._lock:
            try:
                # Close existing context if any
                if self.browser_context:
                    await self.browser_context.close()
                
                # Create user-specific data directory
                user_data_dir = f"{USER_DATA_DIR}/user_{user_id}"
                os.makedirs(user_data_dir, exist_ok=True)
                
                # Windows-specific launch arguments
                self.browser_context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,  # Keep False for QR code visibility
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--window-size=1280,720",
                        "--disable-gpu",
                        "--disable-software-rasterizer"
                    ]
                )
                
                # Get or create page
                self.page = self.browser_context.pages[0] if self.browser_context.pages else await self.browser_context.new_page()
                
                # Navigate to WhatsApp Web with longer timeout
                await self.page.goto("https://web.whatsapp.com", timeout=60000)
                await self.page.wait_for_timeout(8000)  # Wait longer for page to load
                
                # Check if already logged in
                try:
                    await self.page.wait_for_selector('div[id="pane-side"]', timeout=15000)
                    self.is_authenticated = True
                    self.current_user_id = user_id
                    self.db.set_whatsapp_auth_status(user_id, True)
                    logger.info(f"✅ User {user_id} already authenticated")
                    return None
                except:
                    pass
                
                # Wait for QR code with increased timeout and retry
                qr_element = None
                for attempt in range(3):
                    try:
                        qr_element = await self.page.wait_for_selector('canvas', timeout=30000)
                        if qr_element:
                            break
                    except:
                        logger.warning(f"QR attempt {attempt + 1} failed, retrying...")
                        await self.page.reload()
                        await self.page.wait_for_timeout(5000)
                
                if not qr_element:
                    # Take screenshot for debugging
                    screenshot_path = f"debug_screenshot_{user_id}.png"
                    await self.page.screenshot(path=screenshot_path)
                    logger.error(f"QR code not found. Screenshot saved to {screenshot_path}")
                    return None
                
                qr_screenshot = await qr_element.screenshot()
                qr_path = f"whatsapp_qr_user_{user_id}.png"
                with open(qr_path, "wb") as f:
                    f.write(qr_screenshot)
                
                logger.info(f"✅ QR code saved to {qr_path}")
                
                # Start monitoring login
                self._auth_tasks[user_id] = asyncio.create_task(self._monitor_login_headless(user_id, qr_path))
                
                return qr_path
                
            except Exception as e:
                logger.error(f"❌ QR generation failed for user {user_id}: {e}")
                return None
    
    async def _monitor_login_headless(self, user_id: int, qr_path: str):
        """Monitor for WhatsApp login completion (HEADLESS MODE)"""
        try:
            # Wait for login (up to 2 minutes)
            await self.page.wait_for_selector('div[id="pane-side"]', timeout=120000)
            self.is_authenticated = True
            self.current_user_id = user_id
            self.db.set_whatsapp_auth_status(user_id, True)
            
            # Notify user with photo using FSInputFile
            if self.bot:
                if os.path.exists(qr_path):
                    try:
                        from aiogram.types import FSInputFile
                        photo = FSInputFile(qr_path)
                        await self.bot.send_photo(
                            user_id,
                            photo,
                            caption="✅ *WHATSAPP AUTHENTICATED!* ✅\n\nYour WhatsApp is now connected.\n\nUse `/scan` to start your first campaign!",
                            parse_mode="Markdown"
                        )
                        os.remove(qr_path)
                    except Exception as photo_err:
                        logger.error(f"Failed to send QR photo: {photo_err}")
                        await self.bot.send_message(
                            user_id,
                            "✅ *WHATSAPP AUTHENTICATED!* ✅\n\nYour WhatsApp is now connected.\n\nUse `/scan` to start your first campaign!",
                            parse_mode="Markdown"
                        )
                else:
                    await self.bot.send_message(
                        user_id,
                        "✅ *WHATSAPP AUTHENTICATED!* ✅\n\nYour WhatsApp is now connected.\n\nUse `/scan` to start your first campaign!",
                        parse_mode="Markdown"
                    )
            
            logger.info(f"✅ User {user_id} successfully authenticated WhatsApp")
            
        except Exception as e:
            logger.error(f"❌ Login timeout for user {user_id}: {e}")
            if self.bot:
                await self.bot.send_message(
                    user_id,
                    "❌ *WHATSAPP AUTH TIMEOUT* ❌\n\n"
                    "QR code expired. Please use `/auth` again to generate a new QR code.",
                    parse_mode="Markdown"
                )
            if os.path.exists(qr_path):
                os.remove(qr_path)
        finally:
            if user_id in self._auth_tasks:
                del self._auth_tasks[user_id]
    
    async def send_message(self, phone_number: str, message: str, apk_path: Optional[str] = None) -> Tuple[bool, str]:
        """Send WhatsApp message to a phone number"""
        if not self.is_authenticated or not self.page:
            return False, "WhatsApp not authenticated"
        
        try:
            # Clean phone number
            phone_number = re.sub(r'[^0-9+]', '', phone_number)
            if len(phone_number) == 10:
                phone_number = f"+91{phone_number}"
            elif not phone_number.startswith('+'):
                phone_number = f"+{phone_number}"
            
            # Encode message for URL
            encoded_message = requests.utils.quote(message)
            chat_url = f"https://web.whatsapp.com/send?phone={phone_number}&text={encoded_message}"
            
            # Navigate to chat
            await self.page.goto(chat_url)
            await self.page.wait_for_timeout(4000)
            
            # Wait for send button with retry
            for attempt in range(3):
                try:
                    send_btn = await self.page.wait_for_selector(
                        'button[data-testid="compose-btn-send"]', 
                        timeout=15000
                    )
                    if send_btn:
                        await send_btn.click()
                        await self.page.wait_for_timeout(3000)
                        return True, "Sent"
                except:
                    pass
                
                # Try Enter key
                try:
                    await self.page.keyboard.press("Enter")
                    await self.page.wait_for_timeout(3000)
                    return True, "Sent"
                except:
                    pass
                
                await asyncio.sleep(2)
            
            return False, "Send button not found"
            
        except Exception as e:
            logger.error(f"Send error to {phone_number}: {e}")
            return False, str(e)[:50]
    
    async def process_task(self, task: Task, user: User, bot: Bot, chat_id: int):
        """Process a scanning and sending task"""
        try:
            self.bot = bot
            
            # Update task status
            self.db.update_task_status(task.task_id, "scanning")
            
            # Generate RC numbers
            rc_numbers = parse_vehicle_range(task.rc_start, task.count)
            total_to_scan = min(len(rc_numbers), MAX_TASK_COUNT)
            rc_numbers = rc_numbers[:total_to_scan]
            
            targets = []
            progress_msg = await bot.send_message(
                chat_id,
                f"🔍 *SCANNING VEHICLES* 🔍\n\n"
                f"📍 *Range:* `{task.rc_start}` → `+{total_to_scan}`\n"
                f"📊 *Total:* {total_to_scan} vehicles\n"
                f"⏳ *Status:* Scanning in progress...",
                parse_mode="Markdown"
            )
            
            # Scan vehicles
            for i, rc in enumerate(rc_numbers):
                # Update progress every 20 vehicles
                if i % 20 == 0 and i > 0:
                    try:
                        progress_bar = generate_progress_bar(i, total_to_scan)
                        await progress_msg.edit_text(
                            f"🔍 *SCANNING VEHICLES* 🔍\n\n"
                            f"📍 *Range:* `{task.rc_start}` → `+{total_to_scan}`\n"
                            f"📊 *Progress:* {progress_bar}\n"
                            f"🎯 *Found:* {len(targets)} numbers\n"
                            f"⏳ *Remaining:* {total_to_scan - i} vehicles",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.debug(f"Progress update error: {e}")
                
                # Fetch vehicle data
                vehicle_data = await fetch_vehicle_info(rc)
                
                if vehicle_data and vehicle_data.get("status") == "success":
                    phone = extract_phone_from_vehicle(vehicle_data)
                    if phone:
                        targets.append({
                            "rc": rc,
                            "phone": phone,
                            "owner": extract_name_from_vehicle(vehicle_data),
                            "insurance_status": extract_insurance_status(vehicle_data)
                        })
                
                # Delay between API calls
                await asyncio.sleep(random.uniform(SCAN_DELAY_MIN, SCAN_DELAY_MAX))
            
            # Update task with targets found
            task.targets_found = len(targets)
            self.db.update_task_status(task.task_id, "sending", targets_found=len(targets))
            
            if not targets:
                await bot.send_message(
                    chat_id,
                    f"❌ *NO NUMBERS FOUND* ❌\n\n"
                    f"📋 *Task ID:* `{task.task_id}`\n"
                    f"📍 *Range:* {task.rc_start} (+{total_to_scan})\n\n"
                    f"No phone numbers found in the scanned range.",
                    parse_mode="Markdown"
                )
                self.db.update_task_status(task.task_id, "completed")
                return
            
            # Check user credits
            required_credits = len(targets) * CREDITS_PER_SUCCESS
            if user.credits < required_credits:
                await bot.send_message(
                    chat_id,
                    f"❌ *INSUFFICIENT CREDITS* ❌\n\n"
                    f"💰 *Balance:* {format_credits(user.credits)}\n"
                    f"💸 *Required:* {format_credits(required_credits)}\n"
                    f"🎯 *Targets:* {len(targets)} numbers\n\n"
                    f"Contact admin to add credits.",
                    parse_mode="Markdown"
                )
                self.db.update_task_status(task.task_id, "failed")
                return
            
            # Check WhatsApp authentication
            if not self.is_authenticated:
                await bot.send_message(
                    chat_id,
                    "❌ *WHATSAPP NOT AUTHENTICATED* ❌\n\n"
                    "Please use `/auth` command first to connect your WhatsApp.\n"
                    "Then start a new scan.",
                    parse_mode="Markdown"
                )
                return
            
            # Get APK path
            apk_path = None
            if user.apk_file_id:
                apk_path = os.path.join(APK_STORAGE_DIR, f"{user.user_id}_{user.apk_file_id}.apk")
                if not os.path.exists(apk_path):
                    apk_path = None
            
            # Get message template
            message_template = user.custom_message if user.custom_message else PRESET_MESSAGES[0]
            
            # Start sending
            await bot.send_message(
                chat_id,
                f"🚀 *STARTING MESSAGE BLAST* 🚀\n\n"
                f"🎯 *Targets:* {len(targets)} numbers\n"
                f"💸 *Credits to use:* {format_credits(required_credits)}\n"
                f"📱 *APK:* {'✅ Uploaded' if apk_path else '❌ Not set'}\n"
                f"⏳ *Estimated time:* {format_time(len(targets) * 12)}",
                parse_mode="Markdown"
            )
            
            # Send messages to all targets
            sent_count = 0
            failed_count = 0
            failed_numbers = []
            failed_reasons = []
            
            for i, target in enumerate(targets):
                # Update progress every 10 messages
                if i % 10 == 0 and i > 0:
                    try:
                        progress_bar = generate_progress_bar(i, len(targets))
                        await progress_msg.edit_text(
                            f"📤 *SENDING MESSAGES* 📤\n\n"
                            f"📊 *Progress:* {progress_bar}\n"
                            f"✅ *Sent:* {sent_count}\n"
                            f"❌ *Failed:* {failed_count}\n"
                            f"💸 *Credits used:* {sent_count * CREDITS_PER_SUCCESS}\n"
                            f"⏳ *ETA:* {format_time((len(targets) - i) * 12)}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                
                # Format message
                format_args = {
                    'rc_number': target['rc'],
                    'owner_name': target['owner'],
                    'insurance_status': target['insurance_status'],
                    'apk_link': "Download the attached APK file" if apk_path else "Contact RTO office"
                }
                
                try:
                    message = message_template.format(**format_args)
                except KeyError as e:
                    message = f"⚠️ RTO ALERT: Vehicle {target['rc']} has pending challan.\nOwner: {target['owner']}"
                
                # Send message with retry
                success = False
                error_msg = ""
                for retry in range(MAX_RETRIES):
                    success, error_msg = await self.send_message(target['phone'], message, apk_path)
                    if success:
                        break
                    await asyncio.sleep(5)
                
                if success:
                    sent_count += 1
                    user.total_sent += 1
                    self.db.deduct_credits_for_send(user.user_id, True)
                else:
                    failed_count += 1
                    failed_numbers.append(target['phone'])
                    failed_reasons.append(f"{target['phone']}: {error_msg}")
                    user.total_failed += 1
                    self.db.deduct_credits_for_send(user.user_id, False)
                
                # Update task stats
                task.messages_sent = sent_count
                task.messages_failed = failed_count
                task.credits_used = sent_count * CREDITS_PER_SUCCESS
                self.db.update_task_status(
                    task.task_id,
                    "sending",
                    messages_sent=sent_count,
                    messages_failed=failed_count,
                    credits_used=sent_count * CREDITS_PER_SUCCESS
                )
                
                # Delay between messages
                await asyncio.sleep(random.uniform(MESSAGE_DELAY_MIN, MESSAGE_DELAY_MAX))
            
            # Task completed
            self.db.update_task_status(task.task_id, "completed")
            
            # Send completion message
            success_rate = (sent_count / len(targets) * 100) if targets else 0
            completion_text = f"""✅ *BLAST COMPLETED* ✅

📊 *Final Statistics:*
━━━━━━━━━━━━━━━━━━━━━
📍 *RC Range:* `{task.rc_start}` → `+{task.count}`
🎯 *Numbers Found:* `{len(targets)}`
✅ *Successfully Sent:* `{sent_count}`
❌ *Failed:* `{failed_count}`
📈 *Success Rate:* `{success_rate:.1f}%`
💸 *Credits Used:* `{sent_count * CREDITS_PER_SUCCESS}`
💰 *Credits Left:* `{user.credits}`
━━━━━━━━━━━━━━━━━━━━━

📋 *Task ID:* `{task.task_id}`"""
            
            await bot.send_message(chat_id, completion_text, parse_mode="Markdown")
            
            # Send failed numbers if any
            if failed_numbers:
                failed_text = "❌ *Failed Numbers:*\n"
                for num in failed_numbers[:20]:
                    failed_text += f"• `{num}`\n"
                if len(failed_numbers) > 20:
                    failed_text += f"\n... and {len(failed_numbers) - 20} more"
                
                await bot.send_message(chat_id, failed_text[:4000], parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Task processing error: {e}\n{traceback.format_exc()}")
            self.db.update_task_status(task.task_id, "failed", error_message=str(e))
            await bot.send_message(chat_id, f"❌ *Task failed:* `{str(e)[:100]}`", parse_mode="Markdown")
    
    async def close(self):
        """Close WhatsApp manager"""
        try:
            if self.browser_context:
                await self.browser_context.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("✅ WhatsApp manager closed")
        except Exception as e:
            logger.error(f"Error closing WhatsApp manager: {e}")
# ============================================================================
# TELEGRAM BOT STATES
# ============================================================================

class BotStates(StatesGroup):
    """FSM states for the bot"""
    waiting_for_rc_start = State()
    waiting_for_count = State()
    waiting_for_custom_message = State()
    waiting_for_admin_user_id = State()
    waiting_for_credits_amount = State()
    waiting_for_apk_file = State()
    waiting_for_broadcast_message = State()

# ============================================================================
# TELEGRAM BOT MANAGER
# ============================================================================

class TelegramBotManager:
    """Main Telegram bot manager"""
    
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.db = Database()
        self.whatsapp = WhatsAppManager(self.db)
        self.whatsapp.bot = self.bot
        self._setup_handlers()
        self._setup_middleware()
    
    def _setup_middleware(self):
        """Setup middleware for the bot"""
        @self.dp.message()
        async def log_middleware(message: Message, handler):
            """Log all messages for debugging"""
            logger.debug(f"Message from {message.from_user.id}: {message.text}")
            return await handler(message)
    
    def _setup_handlers(self):
        """Setup all telegram bot handlers"""
        
        # ====================================================================
        # COMMAND HANDLERS
        # ====================================================================
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: Message):
            """Start command - Register user and show welcome"""
            user = self.db.add_user(
                message.from_user.id,
                message.from_user.username or "",
                message.from_user.first_name or ""
            )
            
            welcome_text = f"""✨ *WELCOME TO {BOT_NAME}* ✨
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 *User:* @{user.username or 'User'}
🆔 *ID:* `{user.user_id}`
💰 *Credits:* {format_credits(user.credits)}
📊 *Stats:* {user.total_sent} sent, {user.total_failed} failed
👑 *Role:* {"Super Admin 👑" if user.is_super_admin else "Admin ⭐" if user.is_admin else "User 👤"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 *FEATURES:*
• WhatsApp QR authentication
• Vehicle RC scanning
• APK upload & distribution
• 2 credits per successful send

📌 *WORKFLOW:*
`/auth` → `/myapk` → `/presets` → `/scan`

💡 *Use `/help` for all commands*"""
            
            await message.answer(welcome_text, parse_mode="Markdown", reply_markup=self._create_main_keyboard(user))
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: Message):
            """Help command - Show all commands"""
            help_text = f"""*📚 {BOT_NAME} COMMANDS* 📚
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*🔐 AUTHENTICATION*
• `/auth` - Connect WhatsApp (QR code)
• `/logout` - Disconnect WhatsApp

*📁 APK MANAGEMENT*
• `/myapk` - Upload your APK file
• `/myapkstatus` - Check APK status

*💬 MESSAGE SETTINGS*
• `/presets` - Choose preset message
• `/mymessage` - Set custom message
• `/resetmessage` - Reset to default

*🔍 SCANNING*
• `/scan` - Start vehicle scan
• `/tasks` - View your tasks
• `/task <id>` - View task details

*💰 ACCOUNT*
• `/credits` - Check credit balance
• `/stats` - View statistics
• `/referral` - Get referral link

*👑 ADMIN COMMANDS* (Admin only)
• `/admin` - Admin panel
• `/listusers` - List all users
• `/addcredits <id> <amt>` - Add credits
• `/setadmin <id>` - Make user admin
• `/broadcast <msg>` - Broadcast message

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*📞 Support:* @SinghSahab99"""
            
            await message.answer(help_text, parse_mode="Markdown")
        
        @self.dp.message(Command("auth"))
        async def cmd_auth(message: Message):
            """Auth command - Generate WhatsApp QR code"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            await message.answer(
                "🔐 *GENERATING WHATSAPP QR CODE* 🔐\n\n"
                "Please wait while I generate your secure QR code...\n"
                "⏳ This may take 10-15 seconds.",
                parse_mode="Markdown"
            )
            
            qr_path = await self.whatsapp.generate_qr_for_user(message.from_user.id)
            
            if qr_path and os.path.exists(qr_path):
                # Use FSInputFile for file sending
                from aiogram.types import FSInputFile
                photo = FSInputFile(qr_path)
                await message.answer_photo(
                    photo,
                    caption="📷 *SCAN THIS QR CODE* 📷\n\n"
                            "1️⃣ Open WhatsApp on your phone\n"
                            "2️⃣ Tap Menu (⋮) → *Linked Devices*\n"
                            "3️⃣ Tap *Link a Device*\n"
                            "4️⃣ Scan this QR code\n\n"
                            "⏳ *Waiting for authentication...*\n"
                            "✅ You'll be notified when connected.",
                    parse_mode="Markdown"
                )
            elif qr_path is None:
                await message.answer(
                    "✅ *WHATSAPP ALREADY CONNECTED* ✅\n\n"
                    "Your WhatsApp is already authenticated.\n"
                    "You can start spreading campaigns!\n\n"
                    "Use `/scan` to begin.",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    "❌ *FAILED TO GENERATE QR CODE* ❌\n\n"
                    "Please try again in a few moments.\n"
                    "If problem persists, contact support.",
                    parse_mode="Markdown"
                )
        
        @self.dp.message(Command("logout"))
        async def cmd_logout(message: Message):
            """Logout command - Disconnect WhatsApp"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                return
            
            self.db.set_whatsapp_auth_status(message.from_user.id, False)
            await message.answer(
                "🔓 *WHATSAPP DISCONNECTED* 🔓\n\n"
                "Your WhatsApp session has been disconnected.\n"
                "Use `/auth` to reconnect.",
                parse_mode="Markdown"
            )
        
        @self.dp.message(Command("myapk"))
        async def cmd_myapk(message: Message, state: FSMContext):
            """MyAPK command - Upload APK file"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            current_status = "✅ *APK uploaded*" if user.apk_file_id else "❌ *No APK uploaded*"
            
            await state.set_state(BotStates.waiting_for_apk_file)
            await message.answer(
                f"📱 *APK MANAGEMENT* 📱\n\n"
                f"{current_status}\n\n"
                f"📥 *Send your APK file* (as document)\n"
                f"📎 Supported format: `.apk`\n"
                f"🔹 Max size: 50MB\n\n"
                f"Send `/cancel` to abort.",
                parse_mode="Markdown"
            )
        
        @self.dp.message(Command("myapkstatus"))
        async def cmd_myapkstatus(message: Message):
            """Check APK status"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            if user.apk_file_id:
                await message.answer(
                    f"✅ *APK STATUS* ✅\n\n"
                    f"📱 *File ID:* `{user.apk_file_id[:20]}...`\n"
                    f"📅 *Status:* Active\n\n"
                    f"Use `/myapk` to upload a new APK.",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    "❌ *NO APK UPLOADED* ❌\n\n"
                    "Use `/myapk` to upload your APK file.\n"
                    "The APK will be sent with your messages.",
                    parse_mode="Markdown"
                )
        
        @self.dp.message(Command("presets"))
        async def cmd_presets(message: Message):
            """Presets command - Show preset messages"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            builder = InlineKeyboardBuilder()
            for idx, preset in enumerate(PRESET_MESSAGES, 1):
                # Get first line of preset as button text
                btn_text = preset.split('\n')[0].strip()
                if len(btn_text) > 40:
                    btn_text = btn_text[:37] + "..."
                builder.button(text=f"{idx}. {btn_text}", callback_data=f"preset_{idx-1}")
            builder.adjust(1)
            
            current_msg = user.custom_message if user.custom_message else "Default preset (1)"
            current_preview = user.custom_message[:100] + "..." if user.custom_message else PRESET_MESSAGES[0][:100] + "..."
            
            await message.answer(
                f"📝 *PRESET MESSAGES* 📝\n\n"
                f"*Current:* `{current_msg[:30]}`\n\n"
                f"*Preview:*\n```\n{current_preview}\n```\n\n"
                f"Choose a preset below:",
                parse_mode="Markdown",
                reply_markup=builder.as_markup()
            )
        
        @self.dp.message(Command("mymessage"))
        async def cmd_mymessage(message: Message, state: FSMContext):
            """Custom message command"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            await state.set_state(BotStates.waiting_for_custom_message)
            await message.answer(
                f"✍️ *SET CUSTOM MESSAGE* ✍️\n\n"
                f"*Current message:*\n"
                f"```\n{user.custom_message[:200] if user.custom_message else 'Default preset'}\n```\n\n"
                f"Send your custom message.\n"
                f"*Placeholders:*\n"
                f"• `{{rc_number}}` - Vehicle number\n"
                f"• `{{owner_name}}` - Owner name\n"
                f"• `{{insurance_status}}` - Insurance status\n"
                f"• `{{apk_link}}` - APK info\n\n"
                f"Send `/cancel` to abort.",
                parse_mode="Markdown"
            )
        
        @self.dp.message(Command("resetmessage"))
        async def cmd_resetmessage(message: Message):
            """Reset to default message"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                return
            
            self.db.save_user_message(user.user_id, "")
            await message.answer(
                "✅ *MESSAGE RESET* ✅\n\n"
                "Your message has been reset to the default preset.\n"
                "Use `/presets` to choose a different preset.",
                parse_mode="Markdown"
            )
        
        @self.dp.message(Command("scan"))
        async def cmd_scan(message: Message, state: FSMContext):
            """Scan command - Start scanning"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            # Check WhatsApp authentication
            if not user.whatsapp_authenticated:
                await message.answer(
                    "❌ *WHATSAPP NOT CONNECTED* ❌\n\n"
                    "Please connect your WhatsApp first using `/auth`\n"
                    "Then scan the QR code with your phone.",
                    parse_mode="Markdown"
                )
                return
            
            await state.set_state(BotStates.waiting_for_rc_start)
            await message.answer(
                "✍️ *ENTER RC NUMBER* ✍️\n\n"
                "Enter the starting RC number.\n"
                "*Format:* `MH12AB1234` or `MH12AB1234`\n\n"
                "*Examples:*\n"
                "• `MH12DE1433`\n"
                "• `UP15DM3100`\n"
                "• `DL9CQ1234`\n\n"
                "Send `/cancel` to abort.",
                parse_mode="Markdown"
            )
        
        @self.dp.message(Command("tasks"))
        async def cmd_tasks(message: Message):
            """Tasks command - View user tasks"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                return
            
            tasks = self.db.get_user_tasks(user.user_id, limit=10)
            if not tasks:
                await message.answer(
                    "📋 *NO TASKS FOUND* 📋\n\n"
                    "You haven't started any campaigns yet.\n"
                    "Use `/scan` to start your first campaign!",
                    parse_mode="Markdown"
                )
                return
            
            text = "📋 *YOUR CAMPAIGNS* 📋\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            for t in tasks:
                status_emoji = {
                    "pending": "⏳",
                    "scanning": "🔍",
                    "sending": "📤",
                    "completed": "✅",
                    "failed": "❌",
                    "cancelled": "⛔"
                }.get(t.status, "❓")
                
                text += f"{status_emoji} *Task:* `{t.task_id}`\n"
                text += f"   📍 *RC:* {t.rc_start} (+{t.count})\n"
                text += f"   📊 *Sent:* {t.messages_sent} | *Failed:* {t.messages_failed}\n"
                text += f"   📅 *Date:* {t.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            
            text += "━━━━━━━━━━━━━━━━━━━━━\n"
            text += f"📊 *Total:* {len(tasks)} campaigns"
            
            await message.answer(text, parse_mode="Markdown")
        
        @self.dp.message(Command("task"))
        async def cmd_task_details(message: Message):
            """Task details command"""
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer("❌ *Usage:* `/task <task_id>`", parse_mode="Markdown")
                return
            
            task_id = parts[1]
            task = None
            
            # Find task by ID
            for t in self.db.tasks.values():
                if t.task_id == task_id or t.task_id.startswith(task_id):
                    task = t
                    break
            
            if not task:
                await message.answer(f"❌ *Task not found:* `{task_id}`", parse_mode="Markdown")
                return
            
            status_emoji = {
                "pending": "⏳ Pending",
                "scanning": "🔍 Scanning",
                "sending": "📤 Sending",
                "completed": "✅ Completed",
                "failed": "❌ Failed"
            }.get(task.status, task.status)
            
            text = f"📋 *TASK DETAILS* 📋\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"🆔 *ID:* `{task.task_id}`\n"
            text += f"📌 *Status:* {status_emoji}\n"
            text += f"📍 *RC Range:* {task.rc_start} (+{task.count})\n"
            text += f"🎯 *Targets Found:* {task.targets_found}\n"
            text += f"✅ *Messages Sent:* {task.messages_sent}\n"
            text += f"❌ *Messages Failed:* {task.messages_failed}\n"
            text += f"💸 *Credits Used:* {task.credits_used}\n"
            text += f"📅 *Created:* {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if task.started_at:
                text += f"🚀 *Started:* {task.started_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            if task.completed_at:
                text += f"🏁 *Completed:* {task.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            if task.error_message:
                text += f"⚠️ *Error:* `{task.error_message[:50]}`\n"
            
            await message.answer(text, parse_mode="Markdown")
        
        @self.dp.message(Command("credits"))
        async def cmd_credits(message: Message):
            """Credits command"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            await message.answer(
                f"💰 *CREDIT BALANCE* 💰\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{format_credits(user.credits)}\n\n"
                f"💡 *Cost per message:* 2 credits\n"
                f"📊 *Total sent:* {user.total_sent}\n"
                f"❌ *Total failed:* {user.total_failed}\n\n"
                f"Contact admin to add credits.",
                parse_mode="Markdown"
            )
        
        @self.dp.message(Command("stats"))
        async def cmd_stats(message: Message):
            """Statistics command"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            total = user.total_sent + user.total_failed
            rate = (user.total_sent / total * 100) if total > 0 else 0
            
            text = f"📊 *YOUR STATISTICS* 📊\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"👤 *User:* @{user.username or user.first_name}\n"
            text += f"🆔 *ID:* `{user.user_id}`\n"
            text += f"👑 *Role:* {'Super Admin' if user.is_super_admin else 'Admin' if user.is_admin else 'User'}\n"
            text += f"━━━━━━━━━━━━━━━━━━━━━\n"
            text += f"📤 *Messages Sent:* `{user.total_sent}`\n"
            text += f"❌ *Messages Failed:* `{user.total_failed}`\n"
            text += f"📈 *Success Rate:* `{rate:.1f}%`\n"
            text += f"💰 *Credits:* {format_credits(user.credits)}\n"
            text += f"📋 *Total Tasks:* `{user.total_tasks}`\n"
            text += f"📅 *Joined:* {user.join_date.strftime('%Y-%m-%d')}\n"
            text += f"⏰ *Last Active:* {user.last_active.strftime('%Y-%m-%d %H:%M')}"
            
            await message.answer(text, parse_mode="Markdown")
        
        @self.dp.message(Command("referral"))
        async def cmd_referral(message: Message):
            """Referral command"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            bot_username = (await self.bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start=ref_{user.user_id}"
            
            await message.answer(
                f"🔗 *REFERRAL PROGRAM* 🔗\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Share this link with friends:\n"
                f"`{ref_link}`\n\n"
                f"*Rewards:*\n"
                f"• Get 10 credits per referral\n"
                f"• Your friend gets 5 credits\n\n"
                f"*Total Referrals:* 0",
                parse_mode="Markdown"
            )
        
        # ====================================================================
        # ADMIN COMMANDS
        # ====================================================================
        
        @self.dp.message(Command("admin"))
        async def cmd_admin(message: Message):
            """Admin panel command"""
            user = self.db.get_user(message.from_user.id)
            if not user or not (user.is_admin or user.is_super_admin):
                await message.answer("❌ *Admin access required*", parse_mode="Markdown")
                return
            
            stats = self.db.get_stats()
            
            text = f"⚙️ *ADMIN PANEL* ⚙️\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"👥 *Users:* {stats['total_users']}\n"
            text += f"⭐ *Admins:* {stats['total_admins']}\n"
            text += f"💰 *Total Credits:* {stats['total_credits']}\n"
            text += f"📊 *Messages Sent:* {stats['total_sent']}\n"
            text += f"📋 *Total Tasks:* {stats['total_tasks']}\n"
            text += f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"📌 *Commands:*\n"
            text += f"• `/listusers` - List all users\n"
            text += f"• `/addcredits <id> <amt>` - Add credits\n"
            text += f"• `/setadmin <id>` - Make admin\n"
            text += f"• `/removeadmin <id>` - Remove admin\n"
            text += f"• `/broadcast <msg>` - Broadcast message\n"
            text += f"• `/statsall` - System statistics"
            
            await message.answer(text, parse_mode="Markdown")
        
        @self.dp.message(Command("listusers"))
        async def cmd_listusers(message: Message):
            """List all users"""
            user = self.db.get_user(message.from_user.id)
            if not user or not (user.is_admin or user.is_super_admin):
                return
            
            users = self.db.get_all_users()
            text = "👥 *ALL USERS* 👥\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for u in users[:30]:
                role = "👑" if u.is_super_admin else "⭐" if u.is_admin else "👤"
                text += f"{role} `{u.user_id}` | @{u.username or 'NoUser'} | {format_credits(u.credits)}\n"
            
            if len(users) > 30:
                text += f"\n... and {len(users) - 30} more users"
            
            await message.answer(text, parse_mode="Markdown")
        
        @self.dp.message(Command("statsall"))
        async def cmd_statsall(message: Message):
            """System statistics"""
            user = self.db.get_user(message.from_user.id)
            if not user or not (user.is_admin or user.is_super_admin):
                return
            
            stats = self.db.get_stats()
            
            text = f"📊 *SYSTEM STATISTICS* 📊\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"👥 *Total Users:* {stats['total_users']}\n"
            text += f"⭐ *Admins:* {stats['total_admins']}\n"
            text += f"💰 *Total Credits:* {stats['total_credits']}\n"
            text += f"📤 *Messages Sent:* {stats['total_sent']}\n"
            text += f"❌ *Messages Failed:* {stats['total_failed']}\n"
            text += f"📋 *Total Tasks:* {stats['total_tasks']}\n"
            text += f"━━━━━━━━━━━━━━━━━━━━━\n"
            text += f"🤖 *Bot Version:* {BOT_VERSION}\n"
            text += f"⏰ *Uptime:* {format_time(int(time.time() - start_time)) if 'start_time' in dir() else 'Unknown'}"
            
            await message.answer(text, parse_mode="Markdown")
        
        @self.dp.message(Command("addcredits"))
        async def cmd_addcredits(message: Message, command: CommandObject):
            """Add credits to user"""
            user = self.db.get_user(message.from_user.id)
            if not user or not (user.is_admin or user.is_super_admin):
                return
            
            args = command.args
            if not args:
                await message.answer("❌ *Usage:* `/addcredits <user_id> <amount>`", parse_mode="Markdown")
                return
            
            parts = args.split()
            if len(parts) != 2:
                await message.answer("❌ *Usage:* `/addcredits <user_id> <amount>`", parse_mode="Markdown")
                return
            
            try:
                target_id = int(parts[0])
                amount = int(parts[1])
            except ValueError:
                await message.answer("❌ *Invalid input.* User ID and amount must be numbers.", parse_mode="Markdown")
                return
            
            target_user = self.db.get_user(target_id)
            if not target_user:
                await message.answer(f"❌ *User not found:* `{target_id}`", parse_mode="Markdown")
                return
            
            self.db.update_user_credits(target_id, amount)
            
            await message.answer(
                f"✅ *CREDITS UPDATED* ✅\n\n"
                f"👤 *User:* @{target_user.username} (`{target_id}`)\n"
                f"➕ *Change:* `{amount:+,}`\n"
                f"💰 *New Balance:* {format_credits(target_user.credits)}",
                parse_mode="Markdown"
            )
            
            # Notify user
            try:
                await self.bot.send_message(
                    target_id,
                    f"💳 *CREDITS UPDATE* 💳\n\n"
                    f"➕ *Amount Added:* `{amount:+,}`\n"
                    f"💰 *New Balance:* {format_credits(target_user.credits)}\n\n"
                    f"Use `/scan` to start a campaign!",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        @self.dp.message(Command("setadmin"))
        async def cmd_setadmin(message: Message, command: CommandObject):
            """Set user as admin"""
            user = self.db.get_user(message.from_user.id)
            if not user or not user.is_super_admin:
                return
            
            args = command.args
            if not args:
                await message.answer("❌ *Usage:* `/setadmin <user_id>`", parse_mode="Markdown")
                return
            
            try:
                target_id = int(args.strip())
            except ValueError:
                await message.answer("❌ *Invalid user ID*", parse_mode="Markdown")
                return
            
            if self.db.set_user_admin(target_id, True):
                target_user = self.db.get_user(target_id)
                await message.answer(
                    f"✅ *USER PROMOTED* ✅\n\n"
                    f"👤 *User:* @{target_user.username if target_user else target_id} (`{target_id}`)\n"
                    f"⭐ *New Role:* Admin",
                    parse_mode="Markdown"
                )
                
                try:
                    await self.bot.send_message(
                        target_id,
                        "🎉 *YOU ARE NOW AN ADMIN* 🎉\n\n"
                        "You have been promoted to Admin!\n"
                        "Use `/admin` to access admin panel.",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            else:
                await message.answer("❌ *Failed to promote user*", parse_mode="Markdown")
        
        @self.dp.message(Command("removeadmin"))
        async def cmd_removeadmin(message: Message, command: CommandObject):
            """Remove admin status"""
            user = self.db.get_user(message.from_user.id)
            if not user or not user.is_super_admin:
                return
            
            args = command.args
            if not args:
                await message.answer("❌ *Usage:* `/removeadmin <user_id>`", parse_mode="Markdown")
                return
            
            try:
                target_id = int(args.strip())
            except ValueError:
                await message.answer("❌ *Invalid user ID*", parse_mode="Markdown")
                return
            
            target_user = self.db.get_user(target_id)
            if target_user and target_user.is_super_admin:
                await message.answer("❌ *Cannot demote super admin*", parse_mode="Markdown")
                return
            
            if self.db.set_user_admin(target_id, False):
                await message.answer(
                    f"✅ *ADMIN REMOVED* ✅\n\n"
                    f"👤 *User:* `{target_id}`\n"
                    f"⭐ *New Role:* User",
                    parse_mode="Markdown"
                )
            else:
                await message.answer("❌ *Failed to remove admin*", parse_mode="Markdown")
        
        @self.dp.message(Command("broadcast"))
        async def cmd_broadcast(message: Message, command: CommandObject):
            """Broadcast message to all users"""
            user = self.db.get_user(message.from_user.id)
            if not user or not (user.is_admin or user.is_super_admin):
                return
            
            msg = command.args
            if not msg:
                await message.answer("❌ *Usage:* `/broadcast <message>`", parse_mode="Markdown")
                return
            
            progress_msg = await message.answer("📢 *Broadcasting message...*", parse_mode="Markdown")
            
            users = self.db.get_all_users()
            sent = 0
            failed = 0
            
            for u in users:
                try:
                    await self.bot.send_message(
                        u.user_id,
                        f"📢 *BROADCAST MESSAGE* 📢\n━━━━━━━━━━━━━━━━━━━━━\n\n{msg}",
                        parse_mode="Markdown"
                    )
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    failed += 1
                    logger.debug(f"Broadcast failed to {u.user_id}: {e}")
            
            await progress_msg.edit_text(
                f"✅ *BROADCAST COMPLETED* ✅\n\n"
                f"📨 *Sent:* {sent} users\n"
                f"❌ *Failed:* {failed} users\n"
                f"👥 *Total:* {len(users)} users",
                parse_mode="Markdown"
            )
        
        # ====================================================================
        # CALLBACK QUERY HANDLERS
        # ====================================================================
        
        @self.dp.callback_query(F.data.startswith("preset_"))
        async def cb_preset(callback: CallbackQuery):
            """Handle preset selection"""
            user = self.db.get_user(callback.from_user.id)
            if not user:
                await callback.answer("Unauthorized", show_alert=True)
                return
            
            idx = int(callback.data.split("_")[-1])
            if 0 <= idx < len(PRESET_MESSAGES):
                preset = PRESET_MESSAGES[idx]
                self.db.save_user_message(user.user_id, preset)
                
                await callback.message.answer(
                    f"✅ *PRESET APPLIED* ✅\n\n"
                    f"📝 *Message preview:*\n"
                    f"```\n{preset[:200]}...\n```\n\n"
                    f"Use `/scan` to start a campaign!",
                    parse_mode="Markdown"
                )
                await callback.answer()
            else:
                await callback.answer("Invalid preset", show_alert=True)
        
        # ====================================================================
        # FSM STATE HANDLERS
        # ====================================================================
        
        @self.dp.message(Command("cancel"))
        async def cmd_cancel(message: Message, state: FSMContext):
            """Cancel current operation"""
            current_state = await state.get_state()
            if current_state is None:
                await message.answer("❌ *No active operation to cancel*", parse_mode="Markdown")
                return
            
            await state.clear()
            user = self.db.get_user(message.from_user.id)
            await message.answer(
                "✅ *Operation cancelled* ✅\n\n"
                "Returning to main menu.",
                parse_mode="Markdown",
                reply_markup=self._create_main_keyboard(user)
            )
        
        @self.dp.message(BotStates.waiting_for_rc_start)
        async def process_rc_start(message: Message, state: FSMContext):
            """Process RC number input"""
            rc_start = message.text.strip().upper()
            
            # Validate RC format
            clean_rc = re.sub(r'[\s\-]', '', rc_start)
            if not re.match(r'^[A-Z]{2}\d{2}[A-Z]{0,2}\d+$', clean_rc):
                await message.answer(
                    "❌ *INVALID RC FORMAT* ❌\n\n"
                    "Please use format: `MH12AB1234` or `MH12AB1234`\n"
                    "Examples:\n"
                    "• `MH12DE1433`\n"
                    "• `UP15DM3100`\n\n"
                    "Send `/cancel` to abort.",
                    parse_mode="Markdown"
                )
                return
            
            await state.update_data(rc_start=clean_rc)
            await state.set_state(BotStates.waiting_for_count)
            await message.answer(
                "✍️ *ENTER NUMBER OF VEHICLES* ✍️\n\n"
                f"*Range:* `{clean_rc}` to `{clean_rc[:-3]}{int(clean_rc[-3:]) + 49}`\n\n"
                f"Enter how many vehicles to scan (max {MAX_TASK_COUNT}):\n"
                f"Example: `50`\n\n"
                f"Send `/cancel` to abort.",
                parse_mode="Markdown"
            )
        
        @self.dp.message(BotStates.waiting_for_count)
        async def process_count(message: Message, state: FSMContext):
            """Process count input"""
            try:
                count = int(message.text.strip())
                if count <= 0 or count > MAX_TASK_COUNT:
                    raise ValueError
            except ValueError:
                await message.answer(
                    f"❌ *INVALID COUNT* ❌\n\n"
                    f"Please enter a number between 1 and {MAX_TASK_COUNT}.\n"
                    f"Example: `50`\n\n"
                    f"Send `/cancel` to abort.",
                    parse_mode="Markdown"
                )
                return
            
            data = await state.get_data()
            rc_start = data['rc_start']
            await state.clear()
            
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            # Check WhatsApp authentication again
            if not user.whatsapp_authenticated:
                await message.answer(
                    "❌ *WHATSAPP NOT CONNECTED* ❌\n\n"
                    "Please connect your WhatsApp first using `/auth`\n"
                    "Then scan the QR code with your phone.",
                    parse_mode="Markdown"
                )
                return
            
            # Create task
            task = self.db.create_task(user.user_id, rc_start, count)
            
            # Start processing
            await message.answer(
                f"✅ *TASK CREATED* ✅\n\n"
                f"🆔 *Task ID:* `{task.task_id}`\n"
                f"📍 *RC Range:* `{rc_start}` → `+{count}`\n"
                f"📊 *Status:* Processing...\n\n"
                f"📌 You'll receive live updates here.\n"
                f"Use `/tasks` to view all your campaigns.",
                parse_mode="Markdown"
            )
            
            # Process task asynchronously
            asyncio.create_task(self.whatsapp.process_task(task, user, self.bot, message.chat.id))
        
        @self.dp.message(BotStates.waiting_for_custom_message)
        async def process_custom_message(message: Message, state: FSMContext):
            """Process custom message input"""
            custom_msg = message.text.strip()
            user = self.db.get_user(message.from_user.id)
            
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            # Validate placeholders (optional, just warn)
            required_placeholders = ['{rc_number}', '{owner_name}']
            missing = [p for p in required_placeholders if p not in custom_msg]
            
            if missing:
                await message.answer(
                    f"⚠️ *WARNING* ⚠️\n\n"
                    f"Your message is missing these placeholders:\n"
                    f"`{', '.join(missing)}`\n\n"
                    f"Add them for dynamic content:\n"
                    f"• `{{rc_number}}` - Vehicle number\n"
                    f"• `{{owner_name}}` - Owner name\n"
                    f"• `{{insurance_status}}` - Insurance status\n"
                    f"• `{{apk_link}}` - APK info\n\n"
                    f"Send `/save` to save anyway, or type your message again.",
                    parse_mode="Markdown"
                )
                # Keep state, wait for user to confirm or edit
                return
            
            self.db.save_user_message(user.user_id, custom_msg)
            await state.clear()
            await message.answer(
                "✅ *CUSTOM MESSAGE SAVED* ✅\n\n"
                f"📝 *Preview:*\n"
                f"```\n{custom_msg[:300]}...\n```\n\n"
                f"Use `/scan` to start a campaign!",
                parse_mode="Markdown",
                reply_markup=self._create_main_keyboard(user)
            )
        
        @self.dp.message(BotStates.waiting_for_apk_file)
        async def process_apk_upload(message: Message, state: FSMContext):
            """Process APK file upload"""
            if not message.document:
                await message.answer(
                    "❌ *INVALID FILE* ❌\n\n"
                    "Please send an APK file.\n"
                    "Format: `.apk`\n\n"
                    "Send `/cancel` to abort.",
                    parse_mode="Markdown"
                )
                return
            
            if not message.document.file_name.endswith('.apk'):
                await message.answer(
                    "❌ *WRONG FILE TYPE* ❌\n\n"
                    f"Expected: `.apk`\n"
                    f"Received: `{message.document.file_name}`\n\n"
                    "Send a valid APK file or `/cancel` to abort.",
                    parse_mode="Markdown"
                )
                return
            
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            file_id = message.document.file_id
            file_name = message.document.file_name
            file_size = message.document.file_size / (1024 * 1024)  # MB
            
            if file_size > 50:
                await message.answer(
                    "❌ *FILE TOO LARGE* ❌\n\n"
                    f"Size: `{file_size:.1f} MB`\n"
                    f"Max: `50 MB`\n\n"
                    "Please upload a smaller APK file.",
                    parse_mode="Markdown"
                )
                return
            
            apk_path = os.path.join(APK_STORAGE_DIR, f"{user.user_id}_{file_id}.apk")
            
            try:
                # Download file
                status_msg = await message.answer("⏳ *Downloading APK...*", parse_mode="Markdown")
                
                file = await self.bot.get_file(file_id)
                await self.bot.download_file(file.file_path, apk_path)
                
                # Save to database
                self.db.save_user_apk(user.user_id, file_id)
                await state.clear()
                
                await status_msg.delete()
                await message.answer(
                    f"✅ *APK UPLOADED SUCCESSFULLY* ✅\n\n"
                    f"📱 *File:* `{file_name}`\n"
                    f"📦 *Size:* `{file_size:.2f} MB`\n\n"
                    f"💡 *Next Steps:*\n"
                    f"1. Choose a message preset: `/presets`\n"
                    f"2. Start scanning: `/scan`\n\n"
                    f"The APK will be sent with your messages.",
                    parse_mode="Markdown",
                    reply_markup=self._create_main_keyboard(user)
                )
                
            except Exception as e:
                logger.error(f"APK download error: {e}")
                await message.answer(
                    f"❌ *UPLOAD FAILED* ❌\n\n"
                    f"Error: `{str(e)[:100]}`\n\n"
                    f"Please try again.",
                    parse_mode="Markdown"
                )
        
        # ====================================================================
        # DEFAULT HANDLER
        # ====================================================================
        
        @self.dp.message()
        async def default_handler(message: Message):
            """Handle unknown messages"""
            user = self.db.get_user(message.from_user.id)
            if not user:
                user = self.db.add_user(message.from_user.id)
            
            await message.answer(
                "❓ *COMMAND NOT RECOGNIZED* ❓\n\n"
                f"Type `/help` to see all available commands.",
                parse_mode="Markdown",
                reply_markup=self._create_main_keyboard(user)
            )
    
    def _create_main_keyboard(self, user: User) -> ReplyKeyboardMarkup:
        """Create main menu keyboard"""
        builder = ReplyKeyboardBuilder()
        
        # Row 1
        builder.row(
            KeyboardButton(text="🔐 /auth"),
            KeyboardButton(text="📱 /myapk")
        )
        
        # Row 2
        builder.row(
            KeyboardButton(text="💬 /presets"),
            KeyboardButton(text="🔍 /scan")
        )
        
        # Row 3
        builder.row(
            KeyboardButton(text="📋 /tasks"),
            KeyboardButton(text="💰 /credits")
        )
        
        # Row 4
        builder.row(
            KeyboardButton(text="📊 /stats"),
            KeyboardButton(text="❓ /help")
        )
        
        # Admin row
        if user and (user.is_admin or user.is_super_admin):
            builder.row(KeyboardButton(text="⚙️ /admin"))
        
        return builder.as_markup(resize_keyboard=True)
    
    async def run(self):
        """Start the bot"""
        try:
            # Initialize WhatsApp manager
            await self.whatsapp.initialize()
            
            # Start polling
            logger.info(f"🤖 {BOT_NAME} v{BOT_VERSION} started!")
            logger.info(f"👑 Super Admin: {SUPER_ADMIN_ID}")
            logger.info(f"📊 Database: {DATABASE_FILE}")
            logger.info(f"📁 APK Storage: {APK_STORAGE_DIR}")
            
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"❌ Bot failed to start: {e}")
            raise
        finally:
            await self.whatsapp.close()

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

# Track start time for uptime
start_time = time.time()

async def main():
    """Main entry point"""
    bot_manager = TelegramBotManager()
    await bot_manager.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)