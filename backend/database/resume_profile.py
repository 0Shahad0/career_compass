from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
import json

from sqlmodel import Session, select

from backend.schemas.profile import UserProfile
from backend.database.crud import create_or_update_profile_review

from backend.database.models import (
    UserProfile as UserProfileModel,
    Education as EducationModel,
    Experience as ExperienceModel,
    Skill as SkillModel,
    UserSkill as UserSkillModel,
    Certification as CertificationModel,
    Project as ProjectModel,
    UserLanguage as UserLanguageModel,
    Achievement as AchievementModel,
    PortfolioLink as PortfolioLinkModel,
)


RESUME_DIR = Path("data/resumes")


def save_resume_file(
    file_content: bytes
) -> str:
    """
    Save the uploaded resume PDF locally
    and return its file path.
    """

    RESUME_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    file_name = f"{uuid4().hex}.pdf"
    file_path = RESUME_DIR / file_name

    file_path.write_bytes(
        file_content
    )

    return str(file_path)


# Parse a date string from the resume
def parse_resume_date(
    value: str | None
):
    if not value:
        return None

    value = value.strip()

    if value.lower() in {
        "present",
        "current",
        "now"
    }:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y-%m",
        "%b %Y",
        "%B %Y",
        "%Y",
    ]

    for date_format in formats:
        try:
            return datetime.strptime(
                value,
                date_format
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def save_extracted_profile(
    session: Session,
    user_id: int,
    profile: UserProfile,
):
    personal = profile.personal_information

    # ---------------------------------
    # User Profile
    # ---------------------------------

    statement = select(
        UserProfileModel
    ).where(
        UserProfileModel.user_id == user_id
    )

    db_profile = session.exec(
        statement
    ).first()

    if db_profile is None:
        db_profile = UserProfileModel(
            user_id=user_id,
            name=personal.name or "",
            email=personal.email or "",
            phone=personal.phone or "",
            location=personal.location or "",
            professional_summary=(
                profile.professional_summary or ""
            ),
        )

        session.add(db_profile)

    else:
        db_profile.name = personal.name or ""
        db_profile.email = personal.email or ""
        db_profile.phone = personal.phone or ""
        db_profile.location = personal.location or ""
        db_profile.professional_summary = (
            profile.professional_summary or ""
        )


    # ---------------------------------
    # Education
    # ---------------------------------

    existing_educations = session.exec(
        select(EducationModel).where(
            EducationModel.user_id == user_id,
            EducationModel.source == "resume",
        )
    ).all()

    for education in existing_educations:
        session.delete(education)

    for education in profile.education:

        db_education = EducationModel(
            user_id=user_id,
            institution=education.institution or "",
            degree=education.degree or "",
            field_of_study=(
                education.field_of_study or ""
            ),
            start_date=education.start_date or "",
            end_date=education.end_date or "",
            source="resume",
        )

        session.add(db_education)


    # ---------------------------------
    # Experience
    # ---------------------------------

    existing_experiences = session.exec(
        select(ExperienceModel).where(
            ExperienceModel.user_id == user_id,
            ExperienceModel.source == "resume",
        )
    ).all()

    for experience in existing_experiences:
        session.delete(experience)

    for experience in profile.experience:

        db_experience = ExperienceModel(
            user_id=user_id,
            title=experience.title or "",
            company=experience.company or "",
            location=experience.location or "",
            description=experience.description or "",
            start_date=parse_resume_date(
                experience.start_date
            ),
            end_date=parse_resume_date(
                experience.end_date
            ),
            source="resume",
        )

        session.add(db_experience)


    # ---------------------------------
    # Skills
    # ---------------------------------

    existing_user_skills = session.exec(
        select(UserSkillModel).where(
            UserSkillModel.user_id == user_id,
            UserSkillModel.source == "resume",
        )
    ).all()

    for user_skill in existing_user_skills:
        session.delete(user_skill)

    for skill in profile.skills:

        skill_name = skill.name.strip()

        if not skill_name:
            continue

        db_skill = session.exec(
            select(SkillModel).where(
                SkillModel.name == skill_name
            )
        ).first()

        if db_skill is None:
            db_skill = SkillModel(
                name=skill_name
            )

            session.add(db_skill)
            session.flush()

        db_user_skill = UserSkillModel(
            user_id=user_id,
            skill_id=db_skill.id,
            source=(
                skill.source.kind
                if skill.source
                else "resume"
            ),
        )

        session.add(db_user_skill)


    # ---------------------------------
    # Certifications
    # ---------------------------------

    existing_certifications = session.exec(
        select(CertificationModel).where(
            CertificationModel.user_id == user_id,
            CertificationModel.source == "resume",
        )
    ).all()

    for certification in existing_certifications:
        session.delete(certification)

    for certification in profile.certifications:

        db_certification = CertificationModel(
            user_id=user_id,
            name=certification.name or "",
            issuer=certification.issuer or "",
            credential_id=(
                certification.credential_id or ""
            ),
            credential_url=(
                str(certification.credential_url)
                if certification.credential_url
                else ""
            ),
            issue_date=certification.issue_date or "",
            expiry_date=certification.expiry_date or "",
            source="resume",
        )

        session.add(db_certification)


    # ---------------------------------
    # Projects
    # ---------------------------------

    existing_projects = session.exec(
        select(ProjectModel).where(
            ProjectModel.user_id == user_id,
            ProjectModel.source == "resume",
        )
    ).all()

    for project in existing_projects:
        session.delete(project)

    for project in profile.projects:

        db_project = ProjectModel(
            user_id=user_id,
            name=project.name or "",
            description=project.description or "",
            url=(
                str(project.url)
                if project.url
                else ""
            ),
            repository_url=(
                str(project.repository_url)
                if project.repository_url
                else ""
            ),
            technologies=", ".join(
                project.technologies
            ),
            source="resume",
        )

        session.add(db_project)

        
        # ---------------------------------
    # Languages
    # ---------------------------------

    existing_languages = session.exec(
        select(UserLanguageModel).where(
            UserLanguageModel.user_id == user_id
        )
    ).all()

    for language in existing_languages:
        session.delete(language)

    for language in profile.languages:

        language_name = language.strip()

        if not language_name:
            continue

        db_language = UserLanguageModel(
            user_id=user_id,
            name=language_name,
        )

        session.add(db_language)


    # ---------------------------------
    # Achievements
    # ---------------------------------

    existing_achievements = session.exec(
        select(AchievementModel).where(
            AchievementModel.user_id == user_id,
            AchievementModel.source == "resume",
        )
    ).all()

    for achievement in existing_achievements:
        session.delete(achievement)

    for achievement in profile.achievements:

        db_achievement = AchievementModel(
            user_id=user_id,
            title=achievement.title or "",
            description=achievement.description or "",
            date=achievement.date or "",
            source="resume",
        )

        session.add(db_achievement)


    # ---------------------------------
    # Professional Links
    # ---------------------------------

    existing_links = session.exec(
        select(PortfolioLinkModel).where(
            PortfolioLinkModel.user_id == user_id,
            PortfolioLinkModel.source == "resume",
        )
    ).all()

    for link in existing_links:
        session.delete(link)

    for link in profile.professional_links:

        db_link = PortfolioLinkModel(
            user_id=user_id,
            url=str(link.url),
            kind=link.kind,
            label=link.label or "",
            source="resume",
            status="processed",
            error_message="",
        )

        session.add(db_link)


    # ---------------------------------
    # Profile Review Draft
    # ---------------------------------

    profile_json = json.dumps(
        profile.model_dump(mode="json"),
        ensure_ascii=False,
    )

    create_or_update_profile_review(
        session=session,
        user_id=user_id,
        profile_data=profile_json,
        review_status="draft",
    )

    return profile