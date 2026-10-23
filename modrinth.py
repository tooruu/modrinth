from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from dataclasses import dataclass
from typing import ClassVar, Self

import requests


class ApiResource:
    token: ClassVar[str | None] = None
    id: str

    def __eq__(self, other: Self) -> bool:
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @staticmethod
    def query_list(items: list[str]) -> str:
        return str(items).replace("'", '"')

    @classmethod
    def api(cls, endpoint: str, **query: str):
        response = requests.get(
            "https://api.modrinth.com/v3" + endpoint,
            params=query,
            timeout=30,
            headers={"Authorization": cls.token, "User-Agent": "version checker"},
        )
        return response.json()

    @classmethod
    def get(cls, slug: str) -> Self:
        name = cls.__name__.lower()
        return cls.from_api(cls.api(f"/{name}/{slug}"))

    def _get_many_of[T: ApiResource](self, cls: type[T]) -> list[T]:
        name = cls.__name__.lower() + "s"
        return list(map(cls.from_api, cls.api(f"/{name}", ids=cls.query_list(getattr(self, name)))))

    @classmethod
    def from_api(cls, data: dict) -> Self:
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass(frozen=True)
class File:
    hashes: dict[str, str]
    url: str
    filename: str
    primary: bool
    size: int
    file_type: str | None

    def __eq__(self, other: Self) -> bool:
        return self.hashes["sha1"] == other.hashes["sha1"]

    def __hash__(self) -> int:
        return hash(self.hashes["sha1"])


@dataclass(eq=False, frozen=True)
class Version(ApiResource):
    id: str
    project_id: str
    name: str
    version_number: str
    game_versions: list[str]
    loaders: list[str]
    files: list[dict]

    def project(self) -> Project:
        return Project.get(self.project_id)

    @property
    def file(self) -> File:
        files = (File(**f) for f in self.files)
        first = next(files)
        return next(filter(lambda f: f.primary, files), first)

    @property
    def url(self) -> str:
        return f"https://modrinth.com/mod/{self.project_id}/version/{self.id}"


@dataclass(eq=False, frozen=True)
class Project(ApiResource):
    id: str
    name: str
    versions: list[str]
    game_versions: list[str]
    loaders: list[str]

    def get_versions(
        self, *, loader: str | None = None, game_version: str | None = None
    ) -> list[Version]:
        return [
            v
            for v in self._get_many_of(Version)
            if (not loader or loader in v.loaders)
            and (not game_version or game_version in v.game_versions)
        ]


@dataclass(eq=False, frozen=True)
class Collection(ApiResource):
    id: str
    name: str
    projects: list[str]

    def get_projects(self) -> list[Project]:
        return self._get_many_of(Project)


@dataclass(eq=False, frozen=True)
class User(ApiResource):
    id: str
    username: str

    def get_collections(self) -> list[Collection]:
        return list(map(Collection.from_api, self.api(f"/user/{self.id}/collections")))


class Args(argparse.Namespace):
    project: str | None
    collection: str | None
    user: str | None

    loader: str
    mc_version: str | None
    token: str


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="Check latest versions of mods on Modrinth")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-p", "--project", help="project ID/slug", metavar="ID")
    group.add_argument("-c", "--collection", help="collection ID", metavar="ID")
    group.add_argument("-u", "--user", help="user ID/name", metavar="ID")

    parser.add_argument("-l", "--loader", help="Mod loader", type=str.lower, required=True)
    parser.add_argument("-mc", "--mc-version", help="Game version", metavar="VERSION")
    parser.add_argument("-t", "--token", help="API token")

    return parser.parse_args(None if sys.argv[1:] else ["--help"], namespace=Args())


def print_project_info(
    project: Project, loader: str, game_version: str | None, padding: int = 0
) -> None:
    name = project.name.ljust(padding)
    if version := max(
        project.get_versions(loader=loader, game_version=game_version),
        key=lambda v: v.version_number,
        default=None,
    ):
        print(f"{name}  {version.url}")
    else:
        print(f"{name}  not supported for {game_version or ''} {loader}")


def main() -> None:
    args = parse_args()
    ApiResource.token = args.token
    if args.user:
        projects = [p for c in User.get(args.user).get_collections() for p in c.get_projects()]
    elif args.collection:
        projects = Collection.get(args.collection).get_projects()
    elif args.project:
        projects = [Project.get(args.project)]

    max_project_name_len = len(max(projects, key=lambda p: len(p.name)).name)
    for project in sorted(projects, key=lambda p: p.name):
        # print_project_info(project, args.loader, args.mc_version, max_project_name_len)
        if version := max(
            project.get_versions(loader=args.loader, game_version=args.mc_version),
            key=lambda v: v.version_number,
            default=None,
        ):
            resp = requests.get(version.file.url, timeout=30)
            with open(version.file.filename, "wb") as f:
                f.write(resp.content)


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        main()
