import time
import uuid
from typing import Optional

from sqlalchemy.orm import Session
from open_webui.internal.db import Base, get_db_context
from open_webui.models.users import Users, UserResponse

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, JSON


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
    def insert_new_template(
        self, user_id: str, form_data: TemplateForm, db: Optional[Session] = None
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
            with get_db_context(db) as db:
                result = Template(**template.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return TemplateModel.model_validate(result)
                else:
                    return None
        except Exception:
            return None

    def get_template_by_id(
        self, template_id: str, db: Optional[Session] = None
    ) -> Optional[TemplateModel]:
        try:
            with get_db_context(db) as db:
                template = db.query(Template).filter_by(id=template_id).first()
                if template:
                    return TemplateModel.model_validate(template)
                return None
        except Exception:
            return None

    def get_templates(self, db: Optional[Session] = None) -> list[TemplateUserResponse]:
        with get_db_context(db) as db:
            all_templates = db.query(Template).order_by(Template.updated_at.desc()).all()

            user_ids = list(set(template.user_id for template in all_templates))

            users = Users.get_users_by_user_ids(user_ids, db=db) if user_ids else []
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

    def get_templates_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> list[TemplateUserResponse]:
        templates = self.get_templates(db=db)
        return [template for template in templates if template.user_id == user_id]

    def update_template_by_id(
        self, template_id: str, form_data: TemplateForm, db: Optional[Session] = None
    ) -> Optional[TemplateModel]:
        try:
            with get_db_context(db) as db:
                template = db.query(Template).filter_by(id=template_id).first()
                if not template:
                    return None
                template.name = form_data.name
                template.description = form_data.description
                template.system_prompt = form_data.system_prompt
                template.tool_ids = form_data.tool_ids or []
                template.feature_ids = form_data.feature_ids or []
                template.updated_at = int(time.time())
                db.commit()
                return TemplateModel.model_validate(template)
        except Exception:
            return None

    def delete_template_by_id(
        self, template_id: str, db: Optional[Session] = None
    ) -> bool:
        try:
            with get_db_context(db) as db:
                db.query(Template).filter_by(id=template_id).delete()
                db.commit()
                return True
        except Exception:
            return False


Templates = TemplatesTable()
