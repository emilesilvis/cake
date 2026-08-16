"""Concrete Trello and GitHub adapters used by the shared Cake module."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib import error, parse, request

from .domain import CakeError, canonical_ref, normalize, parse_slice_contract


TRELLO_API_BASE = "https://api.trello.com/1"
TRELLO_CREDENTIALS_PATH = Path.home() / ".trello" / "credentials"

_DUPLICATE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}


def _duplicate_terms(value: str) -> set[str]:
    """Return conservative lexical terms for GitHub duplicate detection."""

    result: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", value.casefold()):
        if token in _DUPLICATE_STOP_WORDS or len(token) < 3:
            continue
        if token.startswith("explan"):
            token = "explain"
        elif token.startswith("publish"):
            token = "publish"
        elif token.endswith("ing") and len(token) > 6:
            token = token[:-3]
        elif token.endswith("ed") and len(token) > 5:
            token = token[:-2]
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        result.add(token)
    return result


def _duplicate_score(title: str, body: str, issue: dict[str, Any]) -> float:
    """Score only strong lexical matches; uncertain cases remain human decisions."""

    issue_title = str(issue.get("name", ""))
    raw = issue.get("raw") if isinstance(issue.get("raw"), dict) else {}
    issue_body = str(raw.get("body", ""))
    target_title = _duplicate_terms(title)
    existing_title = _duplicate_terms(issue_title)
    target_all = target_title | _duplicate_terms(body)
    existing_all = existing_title | _duplicate_terms(issue_body)
    title_shared = target_title & existing_title
    all_shared = target_all & existing_all

    title_denominator = min(len(target_title), len(existing_title))
    all_denominator = min(len(target_all), len(existing_all))
    title_overlap = len(title_shared) / title_denominator if title_denominator else 0.0
    all_overlap = len(all_shared) / all_denominator if all_denominator else 0.0

    strong_title_match = len(title_shared) >= 2 and title_overlap >= 0.4
    strong_contract_match = len(all_shared) >= 6 and all_overlap >= 0.35
    if not ((strong_title_match and len(all_shared) >= 4) or strong_contract_match):
        return 0.0
    return round((title_overlap * 0.6) + (all_overlap * 0.4), 3)


def _trello_identifier(value: str, kind: str) -> str | None:
    route = {"board": "b", "card": "c"}.get(kind)
    pattern = rf"trello\.com/{route}/([A-Za-z0-9]+)" if route else ""
    match = re.search(pattern, value) if pattern else None
    return match.group(1) if match else None


class TrelloAdapter:
    """Trello adapter for Pantry, Cake Stand, Plate, and Rhythm records."""

    def __init__(self, credentials_path: Path = TRELLO_CREDENTIALS_PATH):
        self.credentials_path = credentials_path

    def _credentials(self) -> dict[str, str]:
        if not self.credentials_path.exists():
            raise CakeError(f"Trello credentials are missing at {self.credentials_path}")
        values: dict[str, str] = {}
        for raw_line in self.credentials_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        if not values.get("API_KEY") or not values.get("API_TOKEN"):
            raise CakeError(f"Trello credentials at {self.credentials_path} are incomplete")
        return values

    def request(self, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        credentials = self._credentials()
        query = parse.urlencode(
            {"key": credentials["API_KEY"], "token": credentials["API_TOKEN"]}
        )
        url = f"{TRELLO_API_BASE}{path}{'&' if '?' in path else '?'}{query}"
        encoded = None
        if data is not None:
            encoded = parse.urlencode(
                {
                    key: str(value).lower() if isinstance(value, bool) else value
                    for key, value in data.items()
                    if value is not None
                }
            ).encode()
        req = request.Request(url, data=encoded, method=method)
        try:
            with request.urlopen(req, timeout=20) as response:
                content = response.read().decode()
                return json.loads(content) if content else None
        except error.HTTPError as exc:
            response_body = exc.read().decode(errors="replace")[:500]
            raise CakeError(f"Trello returned HTTP {exc.code}: {response_body}") from None
        except error.URLError as exc:
            raise CakeError(f"Could not reach Trello: {exc.reason}") from None

    @staticmethod
    def _exact_named(items: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any]:
        matches = [item for item in items if normalize(item.get("name", "")) == normalize(name)]
        if not matches:
            raise CakeError(f"No open Trello {kind} named {name!r} was found")
        if len(matches) > 1:
            raise CakeError(f"More than one open Trello {kind} is named {name!r}; use its URL or ID")
        return matches[0]

    def board(self, reference: str) -> dict[str, Any]:
        identifier = _trello_identifier(reference, "board")
        if identifier or re.fullmatch(r"[a-fA-F0-9]{24}", reference.strip()):
            value = parse.quote(identifier or reference.strip(), safe="")
            return self.request("GET", f"/boards/{value}?fields=name,url,closed,shortLink")
        boards = self.request("GET", "/members/me/boards?fields=name,url,closed,shortLink&filter=open")
        matches = [
            board
            for board in boards
            if normalize(board.get("name", "")) == normalize(reference)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CakeError(f"More than one open Trello board is named {reference!r}; use its URL or ID")
        if re.fullmatch(r"[A-Za-z0-9]{8,}", reference.strip()):
            value = parse.quote(reference.strip(), safe="")
            return self.request("GET", f"/boards/{value}?fields=name,url,closed,shortLink")
        raise CakeError(f"No open Trello board named {reference!r} was found")

    def lists(self, board: dict[str, Any], *, include_closed: bool = False) -> list[dict[str, Any]]:
        filter_value = "all" if include_closed else "open"
        return self.request(
            "GET", f"/boards/{board['id']}/lists?fields=name,pos,closed&filter={filter_value}"
        )

    def list(self, board: dict[str, Any], reference: str) -> dict[str, Any]:
        lists = self.lists(board)
        matches = [item for item in lists if item.get("id") == reference]
        if len(matches) == 1:
            return matches[0]
        return self._exact_named(lists, reference, "list")

    def cards(self, board: dict[str, Any], *, include_archived: bool = False) -> list[dict[str, Any]]:
        filter_value = "all" if include_archived else "open"
        fields = "name,desc,url,closed,idBoard,idList,pos,shortLink,due,dueComplete,labels,dateLastActivity"
        return self.request("GET", f"/boards/{board['id']}/cards?fields={fields}&filter={filter_value}")

    def card(self, reference: str) -> dict[str, Any]:
        identifier = _trello_identifier(reference, "card") or reference.strip()
        value = parse.quote(identifier, safe="")
        fields = "name,desc,url,closed,idBoard,idList,pos,shortLink,due,dueComplete,labels,dateLastActivity"
        return self.request("GET", f"/cards/{value}?fields={fields}")

    def locate_card(self, reference: str) -> dict[str, Any]:
        card = self.card(reference)
        board = self.request("GET", f"/boards/{card['idBoard']}?fields=name,url,closed,shortLink")
        trello_list = self.request("GET", f"/lists/{card['idList']}?fields=name,pos,closed")
        return {**card, "board": board, "list": trello_list}

    def create_card(
        self,
        list_id: str,
        *,
        name: str,
        description: str,
        position: str | float = "top",
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/cards",
            {"idList": list_id, "name": name, "desc": description, "pos": position},
        )

    def create_list(
        self,
        board_id: str,
        *,
        name: str,
        position: str | float = "bottom",
    ) -> dict[str, Any]:
        if not name.strip():
            raise CakeError("A Trello list needs a name")
        return self.request(
            "POST",
            "/lists",
            {"idBoard": board_id, "name": name.strip(), "pos": position},
        )

    def update_list(self, list_id: str, *, name: str) -> dict[str, Any]:
        if not name.strip():
            raise CakeError("A Trello list needs a name")
        return self.request(
            "PUT",
            f"/lists/{parse.quote(list_id, safe='')}",
            {"name": name.strip()},
        )

    def update_card(self, card_id: str, **changes: Any) -> dict[str, Any]:
        payload_by_name = {
            "name": "name",
            "description": "desc",
            "list_id": "idList",
            "board_id": "idBoard",
            "closed": "closed",
            "position": "pos",
        }
        payload = {payload_by_name[key]: value for key, value in changes.items() if value is not None}
        if not payload:
            return self.card(card_id)
        return self.request("PUT", f"/cards/{card_id}", payload)

    def plugin_status(self, board: dict[str, Any]) -> dict[str, Any]:
        try:
            plugins = self.request("GET", f"/boards/{board['id']}/plugins")
        except CakeError:
            return {"list_limits_plugin_present": None}
        names = [plugin.get("name", "") for plugin in plugins]
        return {"list_limits_plugin_present": any(normalize(name) == "list limits" for name in names)}

    def checklists(self, card_id: str) -> list[dict[str, Any]]:
        """Return complete checklist state for one card."""

        value = parse.quote(card_id, safe="")
        return self.request(
            "GET",
            f"/cards/{value}/checklists?checkItems=all&checkItem_fields=name,state,pos"
            "&fields=name,pos",
        )

    def create_checklist(self, card_id: str, *, name: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/cards/{parse.quote(card_id, safe='')}/checklists",
            {"name": name, "pos": "bottom"},
        )

    def update_checklist(self, checklist_id: str, *, name: str) -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/checklists/{parse.quote(checklist_id, safe='')}",
            {"name": name},
        )

    def create_check_item(self, checklist_id: str, *, name: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/checklists/{parse.quote(checklist_id, safe='')}/checkItems",
            {"name": name, "pos": "bottom"},
        )

    def update_check_item(
        self,
        card_id: str,
        item_id: str,
        *,
        name: str,
        state: str,
    ) -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/cards/{parse.quote(card_id, safe='')}/checkItem/"
            f"{parse.quote(item_id, safe='')}",
            {"name": name, "state": state},
        )

    def delete_check_item(self, card_id: str, item_id: str) -> None:
        self.request(
            "DELETE",
            f"/cards/{parse.quote(card_id, safe='')}/checkItem/"
            f"{parse.quote(item_id, safe='')}",
        )


def github_issue_parts(reference: str) -> tuple[str, int]:
    match = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", reference)
    if not match:
        match = re.fullmatch(r"([^/\s]+/[^#\s]+)#(\d+)", reference.strip())
    if not match:
        raise CakeError(f"GitHub Slice reference must be an issue URL or owner/repository#number, got {reference!r}")
    return match.group(1), int(match.group(2))


class GitHubAdapter:
    """GitHub issue adapter backed by the authenticated ``gh`` CLI."""

    def _run(self, args: list[str]) -> str:
        completed = subprocess.run(["gh", *args], text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise CakeError(f"GitHub command failed: {message[:500]}")
        return completed.stdout.strip()

    def issue(self, reference: str) -> dict[str, Any]:
        repository, number = github_issue_parts(reference)
        output = self._run(
            [
                "issue",
                "view",
                str(number),
                "--repo",
                repository,
                "--json",
                "number,title,url,state,body",
            ]
        )
        value = json.loads(output)
        contract = parse_slice_contract(value.get("body", ""))
        return {
            "id": f"{repository}#{value['number']}",
            "url": value["url"],
            "name": value.get("title", ""),
            "adapter": "github",
            "canonical_state": normalize(value.get("state", "")),
            **contract,
            "raw": value,
        }

    def issues(
        self, repository: str, *, state: str = "all", query: str = ""
    ) -> list[dict[str, Any]]:
        if state not in {"open", "closed", "all"}:
            raise CakeError(f"Unknown GitHub issue state {state!r}")
        args = [
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            state,
            "--limit",
            "1000",
            "--json",
            "number,title,url,state,body,updatedAt,closedAt",
        ]
        if query.strip():
            args.extend(["--search", query.strip()])
        values = json.loads(self._run(args) or "[]")
        result = []
        for value in values:
            contract = parse_slice_contract(value.get("body", ""))
            result.append(
                {
                    "id": f"{repository}#{value['number']}",
                    "url": value["url"],
                    "name": value.get("title", ""),
                    "adapter": "github",
                    "canonical_state": normalize(value.get("state", "")),
                    **contract,
                    "raw": value,
                }
            )
        return result

    def slices(self, repository: str, query: str = "") -> list[dict[str, Any]]:
        """Return every canonical Cake Slice issue, including terminal history."""

        return [
            issue
            for issue in self.issues(repository, state="all", query=query)
            if issue.get("cake") and issue.get("outcome") and issue.get("success")
        ]

    def similar_issues(self, repository: str, *, title: str, body: str) -> list[dict[str, Any]]:
        """Find likely duplicate issues across the repository, regardless of Slice labels."""

        matches = []
        for issue in self.issues(repository, state="all"):
            score = _duplicate_score(title, body, issue)
            if score:
                matches.append(
                    {
                        "url": issue["url"],
                        "title": issue.get("name", ""),
                        "state": issue.get("canonical_state"),
                        "score": score,
                    }
                )
        return sorted(matches, key=lambda match: (-match["score"], match["url"]))

    def create_issue(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        args = ["issue", "create", "--repo", repository, "--title", title, "--body", body]
        for label in labels or []:
            args.extend(["--label", label])
        url = self._run(args)
        return self.issue(url.splitlines()[-1])

    def ensure_label(
        self,
        repository: str,
        name: str,
        *,
        color: str = "d4a72c",
        description: str = "Canonical Cake Slice",
    ) -> None:
        self._run(
            [
                "label",
                "create",
                name,
                "--repo",
                repository,
                "--color",
                color,
                "--description",
                description,
                "--force",
            ]
        )

    def update_issue(self, reference: str, *, title: str, body: str) -> dict[str, Any]:
        repository, number = github_issue_parts(reference)
        self._run(
            ["issue", "edit", str(number), "--repo", repository, "--title", title, "--body", body]
        )
        return self.issue(reference)

    def close_issue(self, reference: str, *, reason: str | None = None) -> None:
        repository, number = github_issue_parts(reference)
        args = ["issue", "close", str(number), "--repo", repository]
        if reason:
            args.extend(["--comment", reason])
        self._run(args)

    def reopen_issue(self, reference: str) -> None:
        repository, number = github_issue_parts(reference)
        self._run(["issue", "reopen", str(number), "--repo", repository])


def is_github_issue(reference: str | None) -> bool:
    if not reference:
        return False
    try:
        github_issue_parts(reference)
        return True
    except CakeError:
        return False


def refs_equal(left: str | None, right: str | None) -> bool:
    return canonical_ref(left) is not None and canonical_ref(left) == canonical_ref(right)
