from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import UTCDateTime


# Status values are kept as plain strings (not a SQLAlchemy Enum) so the
# worker thread can update them with simple equality comparisons and tests
# can introspect without importing an enum type.
JOB_STATUSES = ("Queued", "Processing", "Done", "Error")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    num_clusters: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="Queued")
    # priority: lower runs sooner. Reorder rewrites this to 0..N for queued rows.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    encoder: Mapped[str] = mapped_column(String(32), nullable=False, default="uni")
    em_iter: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tau: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    out_type: Mapped[str] = mapped_column(String(32), nullable=False, default="allcat")

    clusters: Mapped[list["Cluster"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "slide" | "cluster"
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("jobs.id", ondelete="CASCADE"))
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    patches_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list of paths

    job: Mapped[Job] = relationship(back_populates="clusters")
