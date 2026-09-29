from datetime import datetime, timezone
from sqlmodel import Session, select

from backend.database.models import User, UserProfile, ProfileReview


def get_user_by_email(session: Session, email: str):
    statement = select(User).where(User.email == email)
    return session.exec(statement).first()


def get_user(session: Session, user_id: int):
    return session.get(User, user_id)


def create_user(
    session: Session,
    email: str,
    password_hash: str,
):
    user = User(
        email=email,
        password_hash=password_hash,
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


def create_or_update_profile(
    session: Session,
    user_id: int,
    name: str = "",
    education: str = "",
    location: str = "",
    interests: str = "",
):
    statement = select(UserProfile).where(
        UserProfile.user_id == user_id
    )

    profile = session.exec(statement).first()

    if profile is None:
        profile = UserProfile(
            user_id=user_id,
            name=name,
            education=education,
            location=location,
            interests=interests,
        )
        session.add(profile)
    else:
        profile.name = name
        profile.education = education
        profile.location = location
        profile.interests = interests

    session.commit()
    session.refresh(profile)

    return profile


def get_user_profile(session: Session, user_id: int):
    statement = select(UserProfile).where(
        UserProfile.user_id == user_id
    )

    return session.exec(statement).first()


def create_or_update_profile_review(
    session: Session,
    user_id: int,
    profile_data: str,
    review_status: str = "draft",
):
    statement = select(ProfileReview).where(
        ProfileReview.user_id == user_id
    )

    review = session.exec(statement).first()

    if review is None:
        review = ProfileReview(
            user_id=user_id,
            profile_data=profile_data,
            review_status=review_status,
        )
        session.add(review)
    else:
        review.profile_data = profile_data
        review.review_status = review_status
        review.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(review)

    return review


def get_profile_review(
    session: Session,
    user_id: int,
):
    statement = select(ProfileReview).where(
        ProfileReview.user_id == user_id
    )

    return session.exec(statement).first()