from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    profile: Optional["UserProfile"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    profile_review: Optional["ProfileReview"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    skills: list["UserSkill"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    experiences: list["Experience"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    educations: list["Education"] = Relationship(
       back_populates="user",
       sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    projects: list["Project"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    certifications: list["Certification"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    resume_documents: list["ResumeDocument"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    portfolio_links: list["PortfolioLink"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    career_requests: list["CareerRequestRecord"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    languages: list["UserLanguage"] = Relationship(
       back_populates="user",
       sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    achievements: list["Achievement"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    

class Achievement(SQLModel, table=True):
    __tablename__ = "achievements"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    title: str = ""
    description: str = ""
    date: str = ""
    source: str = "manual"

    user: Optional[User] = Relationship(
        back_populates="achievements"
    )

class UserLanguage(SQLModel, table=True):
    __tablename__ = "user_languages"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    name: str = ""

    user: Optional[User] = Relationship(
        back_populates="languages"
    )

class Education(SQLModel, table=True):
    __tablename__ = "educations"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""

    source: str = "manual"

    user: Optional[User] = Relationship(
        back_populates="educations"
    )

class Certification(SQLModel, table=True):
    __tablename__ = "certifications"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    name: str = ""
    issuer: str = ""
    credential_id: str = ""
    credential_url: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    source: str = "manual"

    user: Optional[User] = Relationship(
        back_populates="certifications"
    )



class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        foreign_key="users.id",
        unique=True,
        index=True
    )

    # Personal Information
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""

    # Professional Summary
    professional_summary: str = ""

    #--------------------------------------------------
    education: str = ""
    interests: str = ""

    user: Optional[User] = Relationship(
        back_populates="profile"
    )

class ProfileReview(SQLModel, table=True):
    __tablename__ = "profile_reviews"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)

    profile_data: str = ""
    review_status: str = "draft"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(
        back_populates="profile_review"
    )


class Skill(SQLModel, table=True):
    __tablename__ = "skills"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)

    user_skills: list["UserSkill"] = Relationship(back_populates="skill")


class UserSkill(SQLModel, table=True):
    __tablename__ = "user_skills"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    skill_id: int = Field(foreign_key="skills.id", index=True)

    
    source: str = "manual" # نهى

    user: Optional[User] = Relationship(back_populates="skills")
    skill: Optional[Skill] = Relationship(back_populates="user_skills")


class Experience(SQLModel, table=True):
    __tablename__ = "experiences"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    title: str = ""
    company: str = ""
    location: str = "" # نهى
    description: str = "" 

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


# 2023 or Jan 2023 or 2023 - Present or Summer 2024
    #start_date:str = ""
   # end_date: str = ""

    
    source: str = "manual" # نهى

  

    user: Optional[User] = Relationship(back_populates="experiences")


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    name: str
    description: str = ""
    url: str = ""
    repository_url: str = ""
    technologies: str = ""
    source: str = "manual"

    user: Optional[User] = Relationship(back_populates="projects")


class ResumeDocument(SQLModel, table=True):
    __tablename__ = "resume_documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    file_path: str
    original_filename: str
    status: str = "uploaded"
    error_message: str = ""
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(back_populates="resume_documents")


class PortfolioLink(SQLModel, table=True):
    __tablename__ = "portfolio_links"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    url: str
    # To find out what type of link this is
    kind: str = "other"
    label: str = ""

    source: str = "website"
    status: str = "pending"
    error_message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional[User] = Relationship(back_populates="portfolio_links")


class CareerRequestRecord(SQLModel, table=True):
    __tablename__ = "career_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    query: str
    response: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional[User] = Relationship(back_populates="career_requests")