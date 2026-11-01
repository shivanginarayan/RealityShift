"""Read public repository readiness without credentials or experiment execution."""
import concurrent.futures
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).parents[1]
API = 'https://api.github.com/repos/shivanginarayan/RealityShift'
PATHS = ['README.md','docs/TRUEFORGE_EVIDENCE.md','docs/COMPLETION_REPORT.md',
         'docs/evidence/nemotron/summary.json','docs/evidence/nemotron/session-tools.jsonl',
         'docs/evidence/nemotron/trace-archive.json','docs/evidence/nemotron/trajectories.zip',
         'docs/evidence/nemotron/heldout-report.json','skills/versions/v0004.yaml',
         'demo/assets/realityshift_trueforge_demo.mp4','demo/assets/realityshift_trueforge_demo.json']

def get(path):
    # No Authorization header, stored token, Git credentials, or provider key.
    with urlopen(Request(API + path, headers={'User-Agent':'RealityShift-public-readiness-check',
                                             'Accept':'application/vnd.github+json'}), timeout=30) as response:
        return json.load(response)

def check_file(path):
    try:
        data = get('/contents/' + path)
        return {'path':path,'public_api_read':True,'size':data['size'],
                'github_url':data['html_url'],'download_url':data.get('download_url')}
    except Exception as error:
        return {'path':path,'public_api_read':False,'error_type':type(error).__name__}

def check():
    repo = get('')
    opening = datetime.fromisoformat('2026-10-30T23:00:00+00:00')
    created = datetime.fromisoformat(repo['created_at'].replace('Z','+00:00'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        links = list(executor.map(check_file,PATHS))
    local = json.loads((ROOT/'demo/assets/realityshift_trueforge_demo.json').read_text())
    return {'checked_utc':datetime.now(timezone.utc).isoformat(),
            'authentication_used':False,'repository':{'public':not repo['private'],
            'fork':repo['fork'],'created_at':repo['created_at'],'created_after_opening':created>=opening,
            'url':repo['html_url'],'project_license':repo.get('license')},
            'links':links,'demo_duration_seconds':local['duration_seconds'],
            'demo_within_two_minutes':local['duration_seconds']<=120,
            'technical_links_ready':not repo['private'] and not repo['fork'] and created>=opening
                                    and all(x['public_api_read'] for x in links) and local['duration_seconds']<=120,
            'original_code_license_decision':'intentionally_unlicensed',
            'submission_complete':False,
            'remaining_user_checks':['Registration/pact/account eligibility','Final team and project fields',
                                     'Proof-of-launch video accepted by portal','Report intentionally unlicensed original-code status',
                                     'Challenge declaration and final submit; judge confirmation'],
            'rules_source':'https://strangerbuilds.com/rules',
            'deadline_utc':'2026-11-09T02:59:00Z','deadline_los_angeles':'2026-11-08T18:59:00-08:00',
            'public_links_keep_available_through':'2026-11-19'}

if __name__=='__main__':
    report=check()
    (ROOT/'docs/submission-readiness.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'technical_links_ready':report['technical_links_ready'],
                      'public_links':sum(x['public_api_read'] for x in report['links']),
                      'total_links':len(report['links']),'repository':report['repository'],
                      'submission_complete':False},indent=2))
    if not report['technical_links_ready']:
        raise SystemExit(1)
