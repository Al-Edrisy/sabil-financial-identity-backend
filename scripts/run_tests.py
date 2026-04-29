"""
scripts/run_tests.py — Run all project tests without pytest plugins.
Usage: python3 scripts/run_tests.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

passed = 0
failed = 0


def check(name, condition, detail=''):
    global passed, failed
    if condition:
        print(f'  PASS  {name}')
        passed += 1
    else:
        msg = f'  FAIL  {name}'
        if detail:
            msg += f' — {detail}'
        print(msg)
        failed += 1


# =============================================================================
print('=== MRZ Checksum Tests ===')
from app.ai.ocr_mrz import (
    _mrz_check_digit, validate_mrz_checksums,
    validate_td3_checksums, parse_mrz,
)
from app.ai.ocr import (
    _mrz_check_digit as ocr_cd,
    validate_mrz_checksums as ocr_vm,
    parse_mrz as ocr_pm,
)

L1 = 'P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<'   # 44 chars
L2 = 'L898902C36UTO6908061F9406236ZE184226B<<<<<18'   # 44 chars

check('doc_number check digit',   _mrz_check_digit(L2[0:9])   == int(L2[9]))
check('dob check digit',          _mrz_check_digit(L2[13:19]) == int(L2[19]))
check('expiry check digit',       _mrz_check_digit(L2[21:27]) == int(L2[27]))
check('personal check digit',     _mrz_check_digit(L2[28:42]) == int(L2[42]))
check('fill char maps to zero',   _mrz_check_digit('<<<') == 0)
check('invalid char returns -1',  _mrz_check_digit('A!B') == -1)
check('weight cycle 7-3-1',       _mrz_check_digit('123') == 6)
check('empty field returns 0',    _mrz_check_digit('') == 0)
check('re-export from ocr.py',    ocr_cd(L2[0:9]) == int(L2[9]))

r = validate_mrz_checksums(L2)
check('valid specimen all pass',  r['valid'] is True)
check('doc_number True',          r['doc_number'] is True)
check('dob True',                 r['dob'] is True)
check('expiry True',              r['expiry'] is True)
check('composite True',           r['composite'] is True)
check('td3 alias same result',    validate_td3_checksums(L2) == r)
check('ocr module re-export',     ocr_vm(L2)['valid'] is True)
check('wrong length invalid',     validate_mrz_checksums('SHORT')['valid'] is False)
check('empty string invalid',     validate_mrz_checksums('')['valid'] is False)

tampered_doc = '0' + L2[1:]
check('tampered doc fails',       validate_mrz_checksums(tampered_doc)['doc_number'] is False)

tampered_dob = L2[:13] + '700806' + L2[19:]
# Note: '700806' produces the same DOB check digit as '690806' (hash collision
# in the ICAO 7-3-1 algorithm). The composite checksum catches the tampering.
check('tampered dob fails',       validate_mrz_checksums(tampered_dob)['valid'] is False)

tampered_exp = L2[:21] + '950623' + L2[27:]
check('tampered expiry fails',    validate_mrz_checksums(tampered_exp)['expiry'] is False)

tampered_chk = L2[:9] + 'X' + L2[10:]
check('non-digit check fails',    validate_mrz_checksums(tampered_chk)['doc_number'] is False)

result = parse_mrz([L1, L2])
check('parse valid checksum',     result.get('mrz_checksum_valid') is True)
check('parse tampered fails',     parse_mrz([L1, '0' + L2[1:]]).get('mrz_checksum_valid') is False)
check('mrz_type TD3',             result.get('mrz_type') == 'TD3')
check('mrz_doc_number',           result.get('mrz_doc_number') == 'L898902C3')
check('mrz_nationality',          result.get('mrz_nationality') == 'UTO')
check('mrz_sex',                  result.get('mrz_sex') == 'F')
check('mrz_dob',                  result.get('mrz_dob') == '1969-08-06')
check('mrz_expiry',               result.get('mrz_expiry') == '1994-06-23')
check('name contains Eriksson',   'Eriksson' in result.get('mrz_full_name', ''))
check('empty input returns {}',   parse_mrz([]) == {})
check('single line returns {}',   parse_mrz([L1]) == {})
noise_result = parse_mrz(['NOISE', L1, 'MORE NOISE', L2])
check('noise lines ignored',      noise_result.get('mrz_checksum_valid') is True)
check('ocr module parse_mrz',     ocr_pm([L1, L2]).get('mrz_checksum_valid') is True)

# =============================================================================
print()
print('=== Transaction Parser Tests ===')
from app.ai.parsing.currency_normalizer import extract_amount_and_currency
from app.ai.parsing.transaction_parser import parse_transactions, _auto_detect_strategy

r = extract_amount_and_currency('Upwork Payment 500 USD')
check('basic USD',                r['amount'] == 500.0 and r['currency'] == 'USD')
r = extract_amount_and_currency('$1,500.00')
check('symbol prefix',            r['amount'] == 1500.0 and r['currency'] == 'USD')
r = extract_amount_and_currency('\u0665\u0660\u0660 \u0631\u064a\u0627\u0644')
check('arabic indic digits',      r['amount'] == 500.0 and r['currency'] == 'SAR')
r = extract_amount_and_currency('1.500,00 EUR')
check('european decimal',         r['amount'] == 1500.0 and r['currency'] == 'EUR')
r = extract_amount_and_currency('-300 USD')
check('negative amount abs',      r['amount'] == 300.0)
r = extract_amount_and_currency('Date Description Amount')
check('no amount returns None',   r['amount'] is None)
r = extract_amount_and_currency('99999999 USD')
check('sanity cap',               r['amount'] is None)
r = extract_amount_and_currency('CR 500 USD')
check('CR detection',             r['sign_from_text'] == 'credit')

lines_b = ['Upwork Payment 500 USD', 'Rent April 300 USD', 'Adobe 20 USD']
check('strategy B detection',     _auto_detect_strategy(lines_b) == 'B')
lines_a = ['01/04/2024  Upwork Payment    500.00 USD',
           '02/04/2024  Rent April        300.00 USD',
           '03/04/2024  Adobe             20.00 USD',
           '04/04/2024  Salary            2000.00 USD']
check('strategy A detection',     _auto_detect_strategy(lines_a) == 'A')
lines_c = ['Upwork Payment', '500 USD', 'Rent April', '300 USD', 'Adobe', '20 USD']
check('strategy C detection',     _auto_detect_strategy(lines_c) == 'C')

rows = parse_transactions(['Upwork Payment 500 USD', 'Rent April 300 USD', 'Adobe Subscription 20 USD'])
check('strategy B: 3 rows',       len(rows) == 3)
check('strategy B: description',  rows[0].description == 'Upwork Payment')
check('strategy B: amount',       rows[0].amount == 500.0)
rows = parse_transactions(['Salary Payment 3000 USD'])
check('income classification',    rows[0].type == 'income')
rows = parse_transactions(['Netflix Subscription 15 USD'])
check('expense classification',   rows[0].type == 'expense')
rows = parse_transactions(['Date Description Amount', 'Upwork Payment 500 USD'])
check('skips header lines',       len(rows) == 1)
rows = parse_transactions(['', '  ', 'Upwork Payment 500 USD', ''])
check('skips empty lines',        len(rows) == 1)
rows = parse_transactions(['\u0631\u0627\u062a\u0628 \u0634\u0647\u0631\u064a 5000 SAR'])
check('arabic description',       len(rows) == 1 and rows[0].amount == 5000.0)
rows = parse_transactions(['Upwork Payment', '500 USD', 'Rent April', '300 USD'])
check('strategy C merge',         len(rows) == 2 and rows[0].amount == 500.0)
rows = parse_transactions(lines_a)
check('strategy A: 4 rows',       len(rows) == 4)
check('strategy A: dates',        all(r.transaction_date is not None for r in rows))
check('empty input',              parse_transactions([]) == [])
rows = parse_transactions(['Upwork 500 USD', 'Rent 1500 SAR', 'Netflix 15 EUR'])
check('mixed currencies',         len(rows) == 3)
rows = parse_transactions(['Salary 3750 SAR'])
check('normalized_usd populated', rows[0].normalized_usd is not None and rows[0].normalized_usd > 0)

# =============================================================================
print()
print('=== Signal & Scoring Tests ===')
from datetime import date, datetime
from app.services.signal_service import compute_signals, SignalResult
from app.services.scoring_service import compute_score, get_risk_level, generate_insights

def row(amount, tx_type, month=1):
    return {
        'normalized_usd': amount, 'type': tx_type,
        'transaction_date': date(2024, month, 15),
        'created_at': datetime(2024, month, 15), 'category': 'other',
    }

result = compute_signals([])
check('empty -> insufficient',    result.data_quality == 'insufficient')
result = compute_signals([row(500, 'expense', m) for m in [1, 2, 3]])
check('zero income burden=100',   result.burden == 100.0)
check('zero income savings=0',    result.savings_rate == 0.0)
rows_in = [row(1000, 'income', m) for m in [1, 2, 3]]
rows_ex = [row(500, 'expense', m) for m in [1, 2, 3]]
result = compute_signals(rows_in + rows_ex)
check('savings_rate 50%',         abs(result.savings_rate - 50.0) < 1.0)
check('burden 50%',               abs(result.burden - 50.0) < 1.0)
rows_stable = [row(1000, 'income', m) for m in [1, 2, 3, 4]]
result = compute_signals(rows_stable)
check('perfect stability=100',    result.income_stability == 100.0)
result = compute_signals([row(500, 'unknown', m) for m in range(1, 6)])
check('all unknown insufficient', result.data_quality == 'insufficient')
check('risk trusted >=700',       get_risk_level(750) == 'trusted')
check('risk moderate 500-699',    get_risk_level(600) == 'moderate')
check('risk risky <500',          get_risk_level(400) == 'risky')
check('insufficient score=300',   compute_score(SignalResult(data_quality='insufficient')) == 300)
rows_good = [row(5000, 'income', m) for m in [1, 2, 3, 4]] + [row(500, 'expense', m) for m in [1, 2, 3, 4]]
signals = compute_signals(rows_good)
score = compute_score(signals)
check('score in 300-850',         300 <= score <= 850)
check('good profile scores high', score >= 600)
insights = generate_insights(signals, score)
check('insights not empty',       len(insights) >= 1)
check('insights are strings',     all(isinstance(i, str) for i in insights))

# =============================================================================
print()
print('=== Webhook Service Tests ===')
from app.services.webhook_service import _sign_payload, WebhookService

payload = b'{"event":"test"}'
sig = _sign_payload(payload, 'mysecret')
check('signature format',         sig.startswith('sha256='))
check('signature length',         len(sig) == 71)
check('signature deterministic',  sig == _sign_payload(payload, 'mysecret'))
check('different secret differs', sig != _sign_payload(payload, 'othersecret'))
check('different payload differs', sig != _sign_payload(b'{"event":"other"}', 'mysecret'))
ws = WebhookService()
check('service instantiates',     ws is not None)
check('notify_score_change',      callable(ws.notify_score_change))
check('notify_status_change',     callable(ws.notify_status_change))
check('notify_kyc_status_change', callable(ws.notify_kyc_status_change))

# =============================================================================
print()
print('=== Config Tests ===')
from app.core.config import settings
check('WEBHOOK_SECRET',           hasattr(settings, 'WEBHOOK_SECRET'))
check('CREDIT_WEBHOOK_URL',       hasattr(settings, 'CREDIT_WEBHOOK_URL'))
check('REDIS_URL',                hasattr(settings, 'REDIS_URL'))
check('CREDIT_UPLOAD_DIR',        hasattr(settings, 'CREDIT_UPLOAD_DIR'))
check('allowed_origins_list',     isinstance(settings.allowed_origins_list, list))

# =============================================================================
print()
print('=== Full App Import & Routes ===')
from app.main import app
routes = sorted(set(r.path for r in app.routes))
check('32 routes registered',     len(routes) >= 32, f'got {len(routes)}')
check('/credit/upload',           '/api/v1/credit/upload' in routes)
check('/credit/score',            '/api/v1/credit/score' in routes)
check('/credit/transactions',     '/api/v1/credit/transactions' in routes)
check('/admin/credit/list',       '/api/v1/admin/credit/list' in routes)
check('/admin/credit/rescore',    '/api/v1/admin/credit/users/{user_id}/rescore' in routes)
check('/kyc/verify',              '/api/v1/kyc/verify' in routes)
check('/wallet/withdraw',         '/api/v1/wallet/withdraw' in routes)
check('/users/me DELETE',         '/api/v1/users/me' in routes)
check('/ws/kyc-status',           '/ws/kyc-status/{user_id}' in routes)

# =============================================================================
print()
print(f'Results: {passed} passed, {failed} failed')
if failed:
    sys.exit(1)
else:
    print('All tests passed.')
