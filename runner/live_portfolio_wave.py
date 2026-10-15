"""Project Runner 8/64 governed owner-wide evidence wave.

At most eight simultaneous GitHub read-only work units. At most 64 analytical tasks
queued as a logical batch. This is NOT 64 agents nor arbitrary project runtime.
Uses Project Runner's exact subject/collision/budget admission for every batch.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import argparse
from runner.portfolio_advancement import AdvancementItem, AdvancementWave
from runner.portfolio_wave_scheduler import WaveExecutionBudget, plan_wave_admission

# Maximum scheduling limits: eight active execution slots, sixty-four
# queued analytical items. These are NOT 64 independent agents.
OUTPUT: Path = Path(".")
OWNER = "thebrazenbeard"
LIMIT = 8
LOGIC = 64
EXPECTED = 89
PATTERN = re.compile(r"[0-9a-f]{40}")
NO_EFFECT = "GITHUB_METADATA_INSPECTION_ONLY"

# Read endpoints and arguments are fixed; never construct arbitrary commands.
def gh(*args: str, deadline=24.0):
    proc = subprocess.run(["gh", *args], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, timeout=deadline,
        check=False, shell=False, encoding="utf-8", errors="replace")
    if proc.returncode:
        raise RuntimeError("GitHub read failed: "+proc.stderr.strip()[:180])
    return json.loads(proc.stdout)

def owner_scope(owner: str, *, expected_count: int) -> tuple[str, ...]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}",owner):
        raise ValueError("unqualified owner")
    if type(expected_count) is not int or not 1 <= expected_count <= 300:
        raise ValueError("unqualified expected scope")
    inventory=gh("repo","list",owner,"--limit","300","--json",
                 "nameWithOwner,isArchived,isPrivate")
    if not isinstance(inventory,list):
        raise ValueError("owner inventory is not a list")
    names=set()
    for row in inventory:
        if not isinstance(row,dict):
            raise ValueError("malformed repository")
        name=row.get("nameWithOwner")
        if (not isinstance(name,str) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",name) or
            name.split("/")[0].casefold()!=owner.casefold() or
            type(row.get("isArchived")) is not bool or
            type(row.get("isPrivate")) is not bool):
            raise ValueError("invalid or cross-owner repository")
        if name.casefold() in {x.casefold() for x in names}:
            raise ValueError("duplicate repository")
        if not row["isArchived"] and name.casefold()!=f"{owner}/{owner}".casefold():
            names.add(name)
    if len(names)!=expected_count:
        raise RuntimeError(f"scope mismatch: requested {expected_count}, live {len(names)}")
    return tuple(sorted(names,key=str.casefold))


def atomic(dest: Path, obj):
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name+".tmp")
    with temp.open("x", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
        f.flush();os.fsync(f.fileno())
    os.replace(temp, dest)

def classify(root_paths, ci, prs):
    paths = set(root_paths)
    source = {
        "PYTHON": "pyproject.toml" in paths or "pytest.ini" in paths or "requirements.txt" in paths,
        "GO": "go.mod" in paths,
        "NODE": "package.json" in paths,
        "RUST": "Cargo.toml" in paths,
        "DOTNET": any(k.endswith(".sln") or k.endswith(".csproj") for k in paths),
    }
    stacks = [k for k,v in source.items() if v]
    if ci.get("conclusion")=="failure":
        return "TRIAGE_EXACT_HEAD_CI", stacks
    if len(prs):
        return "REVIEW_EXISTING_PR_BEFORE_EDIT", stacks
    if not stacks:
        return "QUALIFY_SOURCE_AND_TEST_CONTRACT", stacks
    return "RUN_BOUNDED_LOCAL_SUITE_WHEN_QUALIFIED", stacks

def inspect(repo, lane, logic_slot):
    began=time.time()
    slug=repo.rsplit("/",1)[-1]
    folder=OUTPUT/"subjects"/slug
    if folder.exists():raise FileExistsError(f"subject receipt exists {slug}")
    folder.mkdir(parents=True)
    trace=uuid.uuid4().hex
    attempt={"schema":"PORTAL_PROJECT_RUNNER_8x64_ATTEMPT_V1",
      "repository":repo,"lane":lane,"logic_slot":logic_slot,"trace_id":trace,
      "started_utc":datetime.now(timezone.utc).isoformat(),
      "effect_ceiling":NO_EFFECT,"state":"ATTEMPTED"}
    atomic(folder/"attempt.json",attempt)
    try:
        info=gh("api",f"repos/{repo}")
        if str(info.get("full_name","")).casefold()!=repo.casefold() or info.get("archived"):
            raise RuntimeError("repo identity or active currentness mismatch")
        branch=info.get("default_branch")
        if not isinstance(branch,str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,100}",branch):
            raise RuntimeError("unqualified default branch")
        head=gh("api",f"repos/{repo}/branches/{branch}").get("commit",{}).get("sha")
        if not isinstance(head,str) or not PATTERN.fullmatch(head):
            raise RuntimeError("unverified default branch exact SHA")
        tree=gh("api",f"repos/{repo}/git/trees/{head}")
        paths=[str(v.get("path")) for v in tree.get("tree",[]) if isinstance(v,dict) and v.get("path")]
        prs=gh("api",f"repos/{repo}/pulls?state=open&per_page=100")
        if not isinstance(prs,list):raise RuntimeError("PR results invalid")
        # Do not use the HEAD of a different branch or CI run as current-head proof.
        ci_runs=gh("api",f"repos/{repo}/actions/runs?branch={branch}&per_page=5")
        runs=ci_runs.get("workflow_runs",[]) if isinstance(ci_runs,dict) else []
        current_runs=[x for x in runs if isinstance(x,dict) and x.get("head_sha")==head]
        ci=current_runs[0] if current_runs else {}
        next_action,stacks=classify(paths,ci,prs)
        result={**attempt,"state":"SOURCE_CURRENTNESS_VERIFIED",
            "ended_utc":datetime.now(timezone.utc).isoformat(),
            "default_branch":branch,"head_sha":head,
            "repo_private":bool(info.get("private",False)),
            "root_file_count":len(paths),"root_paths_reviewed":sorted(paths)[:32],
            "detected_stacks":stacks,"open_pr_count":len(prs),
            "open_pr_numbers":sorted([int(p["number"]) for p in prs if isinstance(p,dict) and type(p.get("number")) is int])[:100],
            "current_head_ci_conclusion":ci.get("conclusion"),
            "current_head_ci_id":ci.get("id"),
            "next_action":next_action,
            "source_code_executed":False,"github_repository_mutated":False}
    except Exception as exc:
        result={**attempt,"state":"VERIFIED_HELD",
            "ended_utc":datetime.now(timezone.utc).isoformat(),
            "reason":type(exc).__name__+": "+str(exc)[:200],
            "source_code_executed":False,"github_repository_mutated":False}
    atomic(folder/"final.json",result)
    return result

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner",default="thebrazenbeard")
    parser.add_argument("--expected",required=True,type=int)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--execution-lanes",type=int,default=8)
    parser.add_argument("--logic-slots",type=int,default=64)
    args=parser.parse_args(argv)
    if not 1 <= args.execution_lanes <= 8 or not 1 <= args.logic_slots <= 64:
        raise ValueError("execution lanes limited to 8 and logical queue to 64")
    global OUTPUT, OWNER, LIMIT, LOGIC, EXPECTED
    OUTPUT=args.output.absolute()
    OWNER=args.owner
    LIMIT=args.execution_lanes
    LOGIC=args.logic_slots
    EXPECTED=args.expected
    root=Path(__file__).resolve().parents[1]
    if OUTPUT==root or root in OUTPUT.parents:
        raise ValueError("private portfolio receipts must be outside repository checkout")
    if OUTPUT.exists():
        raise RuntimeError("wave directory already exists; never replay")
    names=owner_scope(OWNER,expected_count=EXPECTED)
    observed=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],
                                     text=True).strip()
    if not PATTERN.fullmatch(observed):
        raise RuntimeError("Project Runner source must be an exact Git commit")
    OUTPUT.mkdir(parents=True)
    # Deterministically bind exactly one distinct source subject per live repo.
    subjects=[]
    for i,repo in enumerate(names):
        subjects.append(AdvancementItem(subject_kind="repository",
            subject_id=repo, repositories=(repo,),
            priority="P2", family_id="portfolio-source-review",
            activity_state="CURRENT_UNQUALIFIED",
            lead_identity=f"logic-{i%LOGIC:02d}",
            reviewer_identities=(),
            action="INSPECT_AND_CLASSIFY_EXACT_SOURCE",
            execution_state="QUEUED", effect_ceiling="NO_EFFECT",
            review_gate="SOURCE_REVIEW_REQUIRED",
            frontier=None, source_status="live inventory only",
            lane_id=f"executor-{i%LIMIT+1:02d}"))
    wave=AdvancementWave(wave_id="portfolio-89-8x64-20261015",
        generated_at=datetime.now(timezone.utc).isoformat(),
        corpus_binding={"binding_kind":"LIVE_OWNER_SCOPE","repositories":len(subjects)},
        identities={f"logic-{i:02d}":"ANALYSIS_TASK_NOT_AGENT" for i in range(LOGIC)},
        policy={"max_execution_lanes":LIMIT,"max_logical_queue":LOGIC,
            "no_protected_effects":True,"real_64_agent_workers":False},
        items=tuple(subjects))
    index={item.subject_id:i for i,item in enumerate(subjects)}
    budget=WaveExecutionBudget(max_parallel=LIMIT,max_per_identity=LIMIT,
                              max_per_family=LIMIT,max_per_lane=1)
    manifest={"schema":"PORTAL_PROJECT_RUNNER_89_WAVE_V1",
       "owner":OWNER,"exact_live_names":list(names),
       "selected_runner_sha":observed,"started_utc":wave.generated_at,
       "execution_lane_limit":LIMIT,"logic_queue_limit":LOGIC,
       "independent_logic_agents":0,
       "source_mutations_authorized":False,
       "execution_profile_qualified_for_89":False,
       "method":"Project Runner plan_wave_admission + 8 ThreadPoolExecutor GitHub read workers"}
    atomic(OUTPUT/"manifest.json",manifest)
    completed=set()
    outputs=[]
    batches=[]
    # Break into windows of <=64 pending logic tasks without asserting 64
    # simultaneous CPU threads or independent LLMs.
    for logical_start in range(0,len(names),LOGIC):
        logical_subjects=set(names[logical_start:logical_start+LOGIC])
        while logical_subjects-completed:
            # Canonical standalone Project Runner accepts occupied collision
            # keys (not a newer PORTAL-only excluded_subjects parameter).
            occupied={f"repository:{name.casefold()}" for name in names
                      if name not in logical_subjects or name in completed}
            plan=plan_wave_admission(wave,budget=budget,
                                     occupied_collision_keys=occupied)
            admitted=[a for a in plan.selected if a.subject_id in logical_subjects]
            if not admitted:
                raise RuntimeError("Project Runner cannot admit pending logical tasks")
            with ThreadPoolExecutor(max_workers=LIMIT,thread_name_prefix="portal-exec") as pool:
                jobs={pool.submit(inspect,a.subject_id,a.lane_id,index[a.subject_id]%LOGIC):a
                      for a in admitted}
                for f in as_completed(jobs):
                    result=f.result()
                    completed.add(result["repository"])
                    outputs.append(result)
                    print(json.dumps({"repository":result["repository"],
                        "state":result["state"],"lane":result["lane"],
                        "action":result.get("next_action")},ensure_ascii=False),flush=True)
            batches.append({"logic_window_start":logical_start,
               "admitted":len(admitted),"subjects":[a.subject_id for a in admitted],
               "selected_budget":plan.summary()})
            atomic(OUTPUT/"batches"/f"batch-{len(batches):02d}.json",batches[-1])
    counts=Counter(x["state"] for x in outputs)
    actions=Counter(x.get("next_action","HELD") for x in outputs)
    result={"schema":"PORTAL_PROJECT_RUNNER_89_FINAL_V1",
       "scope_count":len(names),"receipts":len(outputs),"missing":sorted(set(names)-completed),
       "state_counts":dict(counts),"next_actions":dict(actions),
       "batches":len(batches),"max_concurrent_executions":LIMIT,
       "max_logical_queue":LOGIC,"independent_logic_agents":0,
       "source_code_executed":0,"repositories_modified":0,
       "runtime_source_sha":observed,
       "finished_utc":datetime.now(timezone.utc).isoformat()}
    atomic(OUTPUT/"summary.json",result)
    print("FINAL_SUMMARY="+json.dumps(result,ensure_ascii=False),flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
