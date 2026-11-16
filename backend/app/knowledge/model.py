"""The shape of one knowledge-base file (knowledge/libraries/<library>.json), as a strict model.

One file per library. Adding a library is adding a file: no code changes. The fast tests check every file
against this model (and knowledge/schema.json is the same model written out, for people editing by hand).

Rules the model enforces (docs/SPEC.md section 7e):
- Official sources only, each with an https link, the exact line quoted and the date it was checked.
- A "yes" covers a version and everything after it: {"from": "3.5.0"}.
- A "no" is allowed only as the mirror of a "yes": {"before": V}, where V is the "from" of a "yes" for the same
  capability from the same source (the version that added it). A library that never added a capability has no
  claim for it, and its lookup reads "Not in our knowledge base yet".
- A library whose versions can't be looked up (each product ships its own copy) carries `needs_your_environment`
  with its reason and source, and no claims.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.knowledge.versions import read_version

CAPABILITIES = ("ml_kem_768", "x25519mlkem768", "ml_dsa_65")
Capability = Literal["ml_kem_768", "x25519mlkem768", "ml_dsa_65"]
Role = Literal["tls", "key_exchange", "signatures"]
SourceKind = Literal["release_notes", "changelog", "official_docs", "project_repository"]
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
PURL = re.compile(r"pkg:[a-z0-9.+-]+/(?:[A-Za-z0-9._~%+-]+/)*[A-Za-z0-9._~%+-]+")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(Strict):
    title: str = Field(min_length=3, max_length=200)
    url: str = Field(max_length=500)
    quote: str = Field(min_length=3, max_length=600, description="The exact line from the source, word for word.")
    kind: SourceKind
    checked: str = Field(description="The date the source was opened and checked, YYYY-MM-DD.")

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://") or any(c.isspace() for c in v):
            raise ValueError("a source link must be one https address")
        return v

    @field_validator("checked")
    @classmethod
    def _date(cls, v: str) -> str:
        if not ISO_DATE.fullmatch(v):
            raise ValueError("checked must be a date written YYYY-MM-DD")
        return v


class Package(Strict):
    ecosystem: str = Field(min_length=2, max_length=40)
    purl: str = Field(max_length=200, description="The package address without a version, e.g. pkg:deb/debian/libssl3.")

    @field_validator("purl")
    @classmethod
    def _purl(cls, v: str) -> str:
        if not PURL.fullmatch(v) or "@" in v:
            raise ValueError("purl must be a package address without a version (pkg:type/namespace/name)")
        return v


class Versions(Strict):
    from_: str | None = Field(default=None, alias="from")
    before: str | None = None

    @model_validator(mode="after")
    def _one(self) -> "Versions":
        if (self.from_ is None) == (self.before is None):
            raise ValueError('versions is either {"from": V} (a yes) or {"before": V} (a no)')
        for v in (self.from_, self.before):
            if v is not None and read_version(v) is None:
                raise ValueError(f"{v!r} is not a version the reader can read")
        return self


class Claim(Strict):
    capability: Capability
    versions: Versions
    answer: Literal["yes", "no"]
    source: Source

    @model_validator(mode="after")
    def _shape(self) -> "Claim":
        if self.answer == "yes" and self.versions.from_ is None:
            raise ValueError('a "yes" covers {"from": V}: the version that added it and everything after')
        if self.answer == "no" and self.versions.before is None:
            raise ValueError('a "no" covers {"before": V}: only the versions before the one that added it')
        return self


class EnvironmentOnly(Strict):
    reason: str = Field(min_length=10, max_length=400)
    source: Source


class LibraryFile(Strict):
    schema_: Literal["isogeny.knowledge/1"] = Field(alias="schema")
    library: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$", description="Must equal the file name without .json.")
    label: str = Field(min_length=2, max_length=60)
    roles: list[Role] = Field(min_length=1, description="tls: answers the hybrid TLS question; signatures and key_exchange as named.")
    packages: list[Package] = Field(min_length=1)
    match_names: list[str] = Field(default_factory=list, description="Bare names safe to match when a component has no purl.")
    claims: list[Claim] = Field(default_factory=list)
    needs_your_environment: EnvironmentOnly | None = None
    notes: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def _rules(self) -> "LibraryFile":
        if self.needs_your_environment is not None and self.claims:
            raise ValueError("a library that needs your environment carries no version claims")
        yes = {(c.capability, c.versions.from_, c.source.url) for c in self.claims if c.answer == "yes"}
        seen: dict[tuple[str, str], int] = {}
        for c in self.claims:
            if c.answer == "no" and (c.capability, c.versions.before, c.source.url) not in yes:
                raise ValueError(f'the "no" for {c.capability} before {c.versions.before} has no matching "yes" from '
                                 "the same source: a no is allowed only below the version an official source says added it")
            key = (c.capability, c.answer)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                raise ValueError(f"two {c.answer!r} claims for {c.capability}: their ranges would overlap")
        if "tls" not in self.roles and any(c.capability == "x25519mlkem768" for c in self.claims):
            raise ValueError("a hybrid TLS claim needs the tls role")
        return self
