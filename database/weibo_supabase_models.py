from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base


SupabaseWeiboBase = declarative_base()


class SupabaseWeiboCreator(SupabaseWeiboBase):
    __tablename__ = "weibo_creators"

    user_id = Column(BigInteger, primary_key=True)
    nickname = Column(Text, nullable=False)
    gender = Column(Text, nullable=False)
    avatar = Column(Text, nullable=False)
    desc = Column(Text)
    ip_location = Column(Text)
    follows = Column(Integer, nullable=False)
    fans = Column(Text, nullable=False)
    tag_list = Column(Text)
    note_count = Column(Integer, nullable=False, default=0)
    last_modify_ts = Column(BigInteger, nullable=False)


class SupabaseWeiboNote(SupabaseWeiboBase):
    __tablename__ = "weibo_notes"

    note_id = Column(BigInteger, primary_key=True)
    content = Column(Text, nullable=False)
    post_date = Column(DateTime(timezone=True), nullable=False, index=True)
    liked_count = Column(BigInteger, nullable=False)
    comments_count = Column(BigInteger, nullable=False)
    shared_count = Column(BigInteger, nullable=False)
    last_modify_ts = Column(BigInteger, nullable=False, index=True)
    note_url = Column(Text, nullable=False)
    ip_location = Column(Text)
    image_list = Column(JSONB, nullable=False)
    user_id = Column(BigInteger, nullable=False, index=True)
    nickname = Column(Text, nullable=False)
    gender = Column(Text, nullable=False)
    profile_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True))


class SupabaseWeiboImage(SupabaseWeiboBase):
    __tablename__ = "weibo_images"

    id = Column(Integer, primary_key=True)
    note_id = Column(BigInteger, nullable=False, index=True)
    image_url = Column(Text, nullable=False)
    image_index = Column(Integer, nullable=False)
    is_commercial = Column(Boolean)
    created_at = Column(DateTime(timezone=True))
    is_selfie = Column(Boolean)
