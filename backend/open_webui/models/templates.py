import time
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_async_db_context
from open_webui.models.users import Users, UserResponse

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, JSON, delete, select
from sqlalchemy.ext.asyncio import AsyncSession


####################
# Templates DB Schema
####################


class Template(Base):
    __tablename__ = "template"

    id = Column(String, primary_key=True)
    user_id = Column(String)
    name = Column(String)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    tool_ids = Column(JSON, nullable=True)  # List of tool IDs
    feature_ids = Column(JSON, nullable=True)  # List of feature IDs (web_search, image_generation, etc.)
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class TemplateModel(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    tool_ids: Optional[list[str]] = None
    feature_ids: Optional[list[str]] = None
    created_at: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class TemplateUserResponse(TemplateModel):
    user: Optional[UserResponse] = None


class TemplateForm(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    tool_ids: Optional[list[str]] = None
    feature_ids: Optional[list[str]] = None


class TemplatesTable:
    async def insert_new_template(
        self, user_id: str, form_data: TemplateForm, db: Optional[AsyncSession] = None
    ) -> Optional[TemplateModel]:
        template_id = str(uuid.uuid4())
        timestamp = int(time.time())
        template = TemplateModel(
            id=template_id,
            user_id=user_id,
            name=form_data.name,
            description=form_data.description,
            system_prompt=form_data.system_prompt,
            tool_ids=form_data.tool_ids or [],
            feature_ids=form_data.feature_ids or [],
            created_at=timestamp,
            updated_at=timestamp,
        )

        try:
            async with get_async_db_context(db) as session:
                result = Template(**template.model_dump())
                session.add(result)
                await session.commit()
                await session.refresh(result)
                if result:
                    return TemplateModel.model_validate(result)
                else:
                    return None
        except Exception:
            return None

    async def get_template_by_id(
        self, template_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[TemplateModel]:
        try:
            async with get_async_db_context(db) as session:
                template = await session.get(Template, template_id)
                if template:
                    return TemplateModel.model_validate(template)
                return None
        except Exception:
            return None

    async def get_templates(
        self, user_id: Optional[str] = None, db: Optional[AsyncSession] = None
    ) -> list[TemplateUserResponse]:
        async with get_async_db_context(db) as session:
            query = select(Template).order_by(Template.updated_at.desc())
            if user_id is not None:
                query = query.where(Template.user_id == user_id)
            all_templates = (await session.execute(query)).scalars().all()

            user_ids = list(set(template.user_id for template in all_templates))

            users = await Users.get_users_by_user_ids(user_ids, db=session) if user_ids else []
            users_dict = {user.id: user for user in users}

            templates = []
            for template in all_templates:
                user = users_dict.get(template.user_id)
                templates.append(
                    TemplateUserResponse.model_validate(
                        {
                            **TemplateModel.model_validate(template).model_dump(),
                            "user": user.model_dump() if user else None,
                        }
                    )
                )

            return templates

    async def get_templates_by_user_id(
        self, user_id: str, db: Optional[AsyncSession] = None
    ) -> list[TemplateUserResponse]:
        return await self.get_templates(user_id=user_id, db=db)

    async def update_template_by_id(
        self, template_id: str, form_data: TemplateForm, db: Optional[AsyncSession] = None
    ) -> Optional[TemplateModel]:
        try:
            async with get_async_db_context(db) as session:
                template = await session.get(Template, template_id)
                if not template:
                    return None
                template.name = form_data.name
                template.description = form_data.description
                template.system_prompt = form_data.system_prompt
                template.tool_ids = form_data.tool_ids or []
                template.feature_ids = form_data.feature_ids or []
                template.updated_at = int(time.time())
                await session.commit()
                await session.refresh(template)
                return TemplateModel.model_validate(template)
        except Exception:
            return None

    async def delete_template_by_id(
        self, template_id: str, db: Optional[AsyncSession] = None
    ) -> bool:
        try:
            async with get_async_db_context(db) as session:
                await session.execute(delete(Template).where(Template.id == template_id))
                await session.commit()
                return True
        except Exception:
            return False


Templates = TemplatesTable()
