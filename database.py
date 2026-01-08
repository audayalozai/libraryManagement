"""
نظام إدارة قاعدة البيانات للبوت
يستخدم SQLAlchemy مع SQLite للتخزين الآمن والفعال للبيانات
"""

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from loguru import logger

# إعداد قاعدة البيانات
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///adhkar_bot.db')
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)
#engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}) # تم ازالة التكرار
Base = declarative_base()


# ==========================================
# --- نماذج قاعدة البيانات (Models) ---
# ==========================================

class User(Base):
    """نموذج المستخدم"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
    first_name = Column(String(100))
    username = Column(String(100), nullable=True)
    role = Column(String(20), default="user")  # user, admin, owner
    is_subscribed = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_interaction = Column(DateTime, default=datetime.utcnow)


class Channel(Base):
    """نموذج القناة"""
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String(50), unique=True, index=True)
    title = Column(String(200))
    added_by = Column(Integer)  # user_id من أضاف القناة
    added_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class AdhkarCategory(Base):
    """نموذج فئات الأذكار"""
    __tablename__ = "adhkar_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    category_name = Column(String(50), unique=True, index=True)  # sabah, masaa, aam
    is_enabled = Column(Boolean, default=False)
    start_time = Column(String(5), nullable=True)  # HH:MM
    end_time = Column(String(5), nullable=True)    # HH:MM
    interval_minutes = Column(Integer, default=60)
    last_posted_at = Column(DateTime, nullable=True)
    file_path = Column(String(255))


class Adhkar(Base):
    """نموذج الأذكار الفردية"""
    __tablename__ = "adhkars"
    
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, index=True)
    content = Column(Text)
    added_at = Column(DateTime, default=datetime.utcnow)


class BotConfig(Base):
    """نموذج إعدادات البوت"""
    __tablename__ = "bot_config"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# --- إنشاء الجداول ---
# ==========================================

def init_db():
    """إنشاء جميع الجداول"""
    Base.metadata.create_all(bind=engine)
    logger.info("✅ تم إنشاء جداول قاعدة البيانات بنجاح")


# ==========================================
# --- مدير قاعدة البيانات ---
# ==========================================

class DatabaseManager:
    """مدير العمليات على قاعدة البيانات"""
    
    @staticmethod
    @contextmanager
    def get_db():
        """الحصول على جلسة قاعدة البيانات"""
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"❌ خطأ في قاعدة البيانات: {e}")
            raise
        finally:
            db.close()
    
    # ==================== المستخدمون ====================
    
    @staticmethod
    def add_user(user_id: int, first_name: str, username: str = None, role: str = "user") -> User:
        """إضافة مستخدم جديد"""
        with DatabaseManager.get_db() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                user.last_interaction = datetime.utcnow()
                db.commit()
                return user
            
            new_user = User(user_id=user_id, first_name=first_name, username=username, role=role)
            db.add(new_user)
            db.commit()
            logger.info(f"✅ تم إضافة مستخدم جديد: {user_id}")
            return new_user
    
    @staticmethod
    def get_user(user_id: int) -> User:
        """الحصول على بيانات المستخدم"""
        with DatabaseManager.get_db() as db:
            return db.query(User).filter(User.user_id == user_id).first()
    
    @staticmethod
    def get_user_role(user_id: int) -> str:
        """الحصول على دور المستخدم"""
        user = DatabaseManager.get_user(user_id)
        return user.role if user else "user"
    
    @staticmethod
    def set_user_role(user_id: int, role: str) -> bool:
        """تعيين دور المستخدم"""
        with DatabaseManager.get_db() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                user.role = role
                db.commit()
                logger.info(f"✅ تم تعيين دور {role} للمستخدم {user_id}")
                return True
            return False
    
    @staticmethod
    def get_all_users() -> list:
        """الحصول على جميع المستخدمين"""
        with DatabaseManager.get_db() as db:
            return db.query(User).all()
    
    @staticmethod
    def get_admin_users() -> list:
        """الحصول على جميع المشرفين"""
        with DatabaseManager.get_db() as db:
            return db.query(User).filter(User.role.in_(["admin", "owner"])).all()
    
    # ==================== القنوات ====================
    
    @staticmethod
    def add_channel(channel_id: str, title: str, added_by: int) -> Channel:
        """
        إضافة قناة جديدة (محدثة لتدعم إعادة التفعيل)
        إذا كانت القناة موجودة ولكن غير نشطة (محذوفة)، يتم إعادة تفعيلها.
        """
        with DatabaseManager.get_db() as db:
            existing = db.query(Channel).filter(Channel.channel_id == channel_id).first()
            
            if existing:
                # --- التعديل الجديد: التحقق من الحالة ---
                if existing.is_active == False:
                    existing.is_active = True  # إعادة تفعيل القناة
                    existing.title = title      # تحديث العنوان
                    existing.added_by = added_by # تحديث من أضافها
                    db.commit()
                    logger.info(f"✅ تم إعادة تفعيل القناة: {channel_id}")
                # -----------------------------------------
                return existing
            
            # إذا لم تكن موجودة، نقوم بإضافتها
            new_channel = Channel(channel_id=channel_id, title=title, added_by=added_by)
            db.add(new_channel)
            db.commit()
            logger.info(f"✅ تم إضافة قناة جديدة: {channel_id}")
            return new_channel
    
    @staticmethod
    def get_active_channels() -> list:
        """الحصول على جميع القنوات النشطة (للاستخدام العام في البوت)"""
        with DatabaseManager.get_db() as db:
            return db.query(Channel).filter(Channel.is_active == True).all()
    
    # --- التعديل الجديد: دالة لجلب قنوات مستخدم معين ---
    @staticmethod
    def get_user_channels(user_id: int) -> list:
        """الحصول على القنوات النشطة التي أضافها مستخدم معين"""
        with DatabaseManager.get_db() as db:
            return db.query(Channel).filter(
                Channel.added_by == user_id,
                Channel.is_active == True
            ).all()
    # --------------------------------------------------
    
    @staticmethod
    def delete_channel(channel_id: str) -> bool:
        """حذف قناة"""
        with DatabaseManager.get_db() as db:
            channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
            if channel:
                channel.is_active = False
                db.commit()
                logger.info(f"✅ تم حذف القناة: {channel_id}")
                return True
            return False
    
    # ==================== فئات الأذكار ====================
    
    @staticmethod
    def delete_channel_safe(channel_id: str) -> bool:
        """حذف قناة بأمان (للاستخدام في المهام الخلفية)"""
        with DatabaseManager.get_db() as db:
            channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
            if channel:
                db.delete(channel)
                # db.commit يتم تلقائياً عند الخروج من الـ with
                logger.info(f"✅ تم حذف القناة {channel_id} بنجاح عبر المهمة الدورية.")
                return True
            return False
            
            
    @staticmethod
    def init_categories():
        """تهيئة فئات الأذكار الافتراضية"""
        with DatabaseManager.get_db() as db:
            categories = [
                ("sabah", "06:00", "12:00", "azkar_sabah.txt"),
                ("masaa", "18:00", "22:00", "azkar_masaa.txt"),
                ("aam", None, None, "azkar_aam.txt"),
            ]
            
            for cat_name, start, end, file_path in categories:
                existing = db.query(AdhkarCategory).filter(AdhkarCategory.category_name == cat_name).first()
                if not existing:
                    cat = AdhkarCategory(
                        category_name=cat_name,
                        start_time=start,
                        end_time=end,
                        file_path=file_path
                    )
                    db.add(cat)
            
            db.commit()
            logger.info("✅ تم تهيئة فئات الأذكار")
    
    @staticmethod
    def get_category(category_name: str) -> AdhkarCategory:
        """الحصول على فئة أذكار"""
        with DatabaseManager.get_db() as db:
            return db.query(AdhkarCategory).filter(AdhkarCategory.category_name == category_name).first()
    
    @staticmethod
    def update_category(category_name: str, **kwargs) -> bool:
        """تحديث إعدادات فئة أذكار"""
        with DatabaseManager.get_db() as db:
            category = db.query(AdhkarCategory).filter(AdhkarCategory.category_name == category_name).first()
            if category:
                for key, value in kwargs.items():
                    if hasattr(category, key):
                        setattr(category, key, value)
                db.commit()
                logger.info(f"✅ تم تحديث فئة {category_name}")
                return True
            return False
    
    # ==================== الإعدادات ====================
    
    @staticmethod
    def set_config(key: str, value: str):
        """حفظ إعداد"""
        with DatabaseManager.get_db() as db:
            config = db.query(BotConfig).filter(BotConfig.key == key).first()
            if config:
                config.value = value
                config.updated_at = datetime.utcnow()
            else:
                config = BotConfig(key=key, value=value)
                db.add(config)
            db.commit()
            logger.info(f"✅ تم حفظ الإعداد: {key}")
    
    @staticmethod
    def get_config(key: str) -> str:
        """الحصول على إعداد"""
        with DatabaseManager.get_db() as db:
            config = db.query(BotConfig).filter(BotConfig.key == key).first()
            return config.value if config else None


# تهيئة قاعدة البيانات عند استيراد الملف
init_db()