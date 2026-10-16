"""Explicit file-input prompt workflow; success is generation, never a scan pass."""
from pathlib import Path

from .case_approval import ImplementationApproval, evaluate_case_approval
from .case_prompts import compose_case_prompt
from .command_inputs import load_json_input
from .output import misuse, result
from .report_model import assemble_report


def run_case_command(case_id, *, mode, scan_input, repo_root, approved_case=None,
                     approval_file=None):
    """Reassemble/reprove an imported scan, then compose one bounded case prompt.

    Source text and imported JSON are evidence, not instructions or permission.
    Operator approval is explicit input, bound by the approval workflow. Even a
    matching record permits manual planning only; this function writes no files.
    """
    if type(mode) is not str or mode not in ('review', 'implement'):
        return misuse('Invalid case prompt mode.')
    if mode == 'implement' and approved_case != case_id:
        return misuse('Implement mode requires a matching case selector.')
    if mode == 'review' and (approved_case is not None or approval_file is not None):
        return misuse('Approval options are valid only for implement mode.')
    try:
        root=Path(repo_root)
        scan_record=load_json_input(scan_input)
        report=assemble_report(scan_record,repo_root=root)
        prompt=compose_case_prompt(report,case_id,mode=mode,repo_root=root)
        payload=prompt.to_dict()
        decision=None
        if mode=='implement':
            approval=None
            if approval_file is not None:
                approval=ImplementationApproval.from_dict(load_json_input(approval_file,maximum_bytes=64_000))
            decision=evaluate_case_approval(report,case_id,prompt=prompt,repo_root=root,approval=approval).to_dict()
        complete=mode=='review' and payload['source']['status']=='VERIFIED'
        if complete:
            errors=[]
        elif decision is not None and decision['status']=='denied':
            errors=[{'code':'CASE_APPROVAL_DENIED','message':'The selected case is not approved for the requested planning workflow.'}]
        elif mode=='implement':
            errors=[{'code':'CASE_REVIEW_REQUIRED','message':'Case-specific source and effect review is required; no execution or source-write authority is granted.'}]
        else:
            errors=[{'code':'CASE_SOURCE_UNRESOLVED','message':'Source proof is unresolved; use the lookup plan before proposing a change.'}]
        return result('prompt',complete=complete,errors=errors,data={
            'scope':'case_prompt_generation_only','analysis_performed':False,
            'prompt':payload,'prompt_digest':prompt.digest,'approval':decision,
        })
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RuntimeError,OverflowError):
        return result('prompt',complete=False,errors=[{
            'code':'CASE_INPUT_UNAVAILABLE',
            'message':'Explicit case inputs or source proof are invalid or unavailable.',
        }],data={'scope':'case_prompt_generation_only','analysis_performed':False})
