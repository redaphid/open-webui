from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from open_webui.models.templates import (
    TemplateForm,
    TemplateUserResponse,
    TemplateModel,
    Templates,
)
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_verified_user
from open_webui.internal.db import get_session
from sqlalchemy.orm import Session

router = APIRouter()

############################
# GetTemplates
############################


@router.get("/", response_model=list[TemplateUserResponse])
async def get_templates(
    user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    """Get all templates for the current user."""
    return Templates.get_templates_by_user_id(user.id, db=db)


############################
# CreateNewTemplate
############################


@router.post("/create", response_model=Optional[TemplateModel])
async def create_new_template(
    form_data: TemplateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Create a new chat template."""
    template = Templates.insert_new_template(user.id, form_data, db=db)

    if template:
        return template
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.DEFAULT(),
    )


############################
# GetTemplateById
############################


@router.get("/{template_id}", response_model=Optional[TemplateModel])
async def get_template_by_id(
    template_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Get a template by ID."""
    template = Templates.get_template_by_id(template_id, db=db)

    if template:
        if template.user_id == user.id or user.role == "admin":
            return template
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=ERROR_MESSAGES.NOT_FOUND,
    )


############################
# UpdateTemplateById
############################


@router.post("/{template_id}/update", response_model=Optional[TemplateModel])
async def update_template_by_id(
    template_id: str,
    form_data: TemplateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Update a template by ID."""
    template = Templates.get_template_by_id(template_id, db=db)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if template.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    updated_template = Templates.update_template_by_id(template_id, form_data, db=db)
    if updated_template:
        return updated_template

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.DEFAULT(),
    )


############################
# DeleteTemplateById
############################


@router.delete("/{template_id}/delete", response_model=bool)
async def delete_template_by_id(
    template_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Delete a template by ID."""
    template = Templates.get_template_by_id(template_id, db=db)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if template.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    result = Templates.delete_template_by_id(template_id, db=db)
    return result
