"""Every worked example on the Rules page, recomputed by the application's code.

GENERATED from the catalog's examples - each function is the computation an
example describes, written out as ordinary Python. The test asserts the result
the catalog states (`example.expect`), so a change to a formula, threshold or
filter that alters an example fails here and the Rules page text must be
re-checked. Every rule marked `verified` in the catalog must have an entry.

Run: PYTHONPATH=src python -m pytest tests/test_rules_examples.py -v
"""
# ruff: noqa: E731, E741, PLC3002, PLW0108, ARG005, C408, RUF015, F841

import json
import os

import pytest

from app.services import rules_catalog

# Snapshot capture, for authoring only: with RULES_EXAMPLES_CAPTURE=<file>,
# each example's live result is written there instead of asserted.
_CAPTURE = os.environ.get("RULES_EXAMPLES_CAPTURE")

def ex_content_studio__cs_account_evidence_lines():
    return __import__('app.services.extractors.content_studio', fromlist=['_'])._label_block('A', [('Business description', 'Maker of motorcycles'), ('Industry', 'Automotive')])

def ex_content_studio__cs_hiring_clusters():
    return [(c['title'], c['posting_count'], c['hp_relevance_band']) for c in __import__('app.services.extractors.content_studio', fromlist=['_'])._derive_role_proxy_personas([{'title': 'Senior Data Engineer - GSI', 'seniority': 'mid_senior', 'categories': '["data"]'}, {'title': 'Data Engineer', 'seniority': 'mid_senior', 'categories': '["information_technology"]'}, {'title': 'IT Intern', 'seniority': 'intern', 'categories': '["information_technology"]'}, {'title': 'Security Supervisor', 'seniority': 'manager', 'categories': '["military_and_protective_services"]'}, {'title': 'IT Infrastructure Manager', 'seniority': 'manager', 'categories': '["information_technology"]'}])]

def ex_content_studio__cs_grounding_corpus():
    return __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['Number Of Employees Range: 4500', 'growth 12%']).unsourced_numbers('Your 4,500 staff and 47% growth')

def ex_content_studio__cs_persona_selection():
    return [__import__('app.services.hp.buyer_personas', fromlist=['_']).match_role(t) for t in ('Chief Financial Officer (CFO)', 'Head of Procurement', 'Chief Marketing Officer')]

def ex_content_studio__cs_persona_evidence():
    return __import__('app.services.hp.buyer_personas', fromlist=['_']).generation_evidence('cfo')

def ex_content_studio__cs_named_vs_role():
    return (__import__('app.services.extractors.content_studio', fromlist=['_'])._is_named_person({'kind': 'client_role', 'is_filled': False}), __import__('app.services.extractors.content_studio', fromlist=['_'])._is_named_person({'kind': 'client_role', 'is_filled': True}))

def ex_content_studio__cs_one_pager_contract():
    return __import__('app.services.extractors.content_studio', fromlist=['_'])._parse_pillars([{'heading': 'Fleet cost', 'challenge': ''}, {'heading': 'Security baseline', 'challenge': 'Mixed estate', 'hp_response': 'HP Wolf Security', 'evidence_used': ['A1', 'A9']}], {'A1': 'Technology estate: ...'})

def ex_content_studio__cs_line_eligibility():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g4_line_eligibility({'hp_products': ['HP Care Pack Services'], 'opening': 'A Poly Studio bar could help your finance team.'}, 'cfo')

def ex_content_studio__cs_line_qualifiers():
    return __import__('app.services.hp.buyer_personas', fromlist=['_']).qualifier('cfo', 'HP Anyware / DaaS')

def ex_content_studio__cs_one_line_max():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g5_one_line_maximum({'hp_products': ['HP Wolf Security'], 'opening': 'HP Wolf Security and HP Elite / Pro PCs together.'})

def ex_content_studio__cs_ask_bound():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g6_ask_bound({'cta': 'Could I send you pricing for a 200-seat refresh?'}, 'cfo')

def ex_content_studio__cs_validator():
    return (lambda cs, G: (lambda corp: cs._validate_asset({'asset': {'subject_line': 'Quick question about your PCs', 'opening': 'Your new Cikarang assembly plant needs devices.', 'body_sections': [{'text': 'At HP, we see 47% faster rollouts with HP Elite / Pro PCs.'}], 'cta': 'Would a short briefing on fleet economics help?', 'hp_products': ['HP Elite / Pro PCs'], 'evidence_used': ['A1']}}, cs.CONTENT_TYPE_CONTRACTS['email'], {'id': 'cfo', 'kind': 'client_role', 'is_filled': False}, {'A1': 'Business description: Cikarang assembly plant'}, corp, G.GroundingReport(corp, []), []))(G.Corpus(['Cikarang assembly plant'])))(__import__('app.services.extractors.content_studio', fromlist=['_']), __import__('app.services.extractors.grounding', fromlist=['_']))

def ex_content_studio__cs_g1():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g1_unsourced_numbers({'opening': 'Your 4,500 staff and 47% growth'}, __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['Number Of Employees Range: 4500', 'growth 12%']))

def ex_content_studio__cs_g2():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g2_evidence_labels_valid({'evidence_used': ['A1', 'A9']}, ['A1', 'A2', 'P1'])

def ex_content_studio__cs_g3():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g3_evidence_coverage({'evidence_used': ['A1'], 'opening': 'Technology plays a critical role.'}, {'A1': 'Business description: automotive assembly plant in Cikarang'})

def ex_content_studio__cs_g7():
    return (__import__('app.services.hp.content_gates', fromlist=['_']).g7_name_leak({'opening': 'Dear Budi Santoso, thanks.'}, False, ['budi santoso']), __import__('app.services.hp.content_gates', fromlist=['_']).g7_name_leak({'opening': 'Dear CIO, thanks.'}, False, []))

def ex_content_studio__cs_g8():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g8_competitors({'opening': 'Unlike our Dell fleet, Lenovo devices are outdated and costly.'}, ['dell', 'lenovo'])

def ex_content_studio__cs_g9():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g9_banned_phrases({'opening': 'We offer industry-leading devices! Move before the Windows 10 end of support deadline. Your team is great, however, there is more to gain.'})

def ex_content_studio__cs_g10():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g10_industry_as_justification({'opening': 'Because you operate in automotive manufacturing, your systems must be reliable.'}, 'automotive manufacturing / Motor Vehicle Manufacturing')

def ex_content_studio__cs_g11():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g11_empty_string_fill({'opening': 'x', 'cta': '  '}, ['opening', 'cta'])

def ex_content_studio__cs_g12():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g12_word_budget({'opening': ' '.join(['w'] * 100)}, 'email')

def ex_content_studio__cs_g13():
    return __import__('app.services.hp.content_gates', fromlist=['_']).g13_pillar_count({'pillars': [{'heading': 'h', 'challenge': 'c', 'evidence_used': ['A1']}]}, 'one_pager')

def ex_content_studio__cs_fallback():
    return __import__('app.services.extractors.content_studio', fromlist=['_'])._safe_fallback_asset(__import__('app.services.extractors.content_studio', fromlist=['_']).CONTENT_TYPE_CONTRACTS['email'], {'title': 'Chief Financial Officer'}, 'Astra', 'HP Elite & Pro PCs', {'A1': 'Business description: Maker of motorcycles', 'P1': 'Role: Chief Financial Officer'})

def ex_content_studio__cs_greeting():
    return [__import__('app.services.extractors.content_studio', fromlist=['_'])._compose_greeting(p, __import__('app.services.extractors.content_studio', fromlist=['_']).CONTENT_TYPE_CONTRACTS['email']) for p in ({'kind': 'client_role', 'is_filled': True, 'full_name': 'Budi Santoso'}, {'kind': 'client_role', 'is_filled': False, 'title': 'Chief Financial Officer'}, {'kind': 'client_role', 'is_filled': False, 'title': 'VP / Head of Information Technology'})]

def ex_content_studio__cs_proof_point():
    return __import__('app.services.hp.case_studies', fromlist=['_'])._score({'industry': 'Industrial Manufacturing', 'signal_tags': ['Fleet-Refresh'], 'outcome': 'cut downtime', 'source_tier': 'T0', 'challenge': 'x', 'customer': 'Acme'}, __import__('app.services.hp.case_studies', fromlist=['_']).normalise_industry('automation machinery manufacturing / Other Industrial Machinery Manufacturing'), __import__('app.services.hp.case_studies', fromlist=['_']).signals_for_opportunity('HP Elite & Pro PCs', 'email'))

def ex_content_studio__cs_audit_ledger():
    return __import__('app.services.hp.content_audit', fromlist=['_']).is_clean({'audit_unsourced_numbers.csv': 0, 'audit_other.csv': 2})

def ex_content_studio__cs_claim_quality():
    return [__import__('app.services.hp.claim_quality', fromlist=['_']).assess({'text': t}) for t in ('Up to 14 hours of battery life on select configurations', 'Raw power that stops what others cannot see', 'HP EliteBook 8 G2i 14-inch Next Gen AI PC', 'and more')]

def ex_content_studio__cs_country_guardrails():
    return [d.as_dict() for d in __import__('app.services.hp.guardrails', fromlist=['_']).approve_rulebook_facts({'rule_label': 'WOLF 01', 'allowed_facts': ["HP Wolf Security is the world's most secure PC protection", 'Sure View is available on EliteBook'], 'conditions': []}, 'Jakarta, Indonesia')[1]]

def ex_content_studio__cs_tier_language():
    return __import__('app.services.hp.guardrails', fromlist=['_']).tier_language_faults('HP WXP is relevant to this opportunity. Astra requires endpoint protection.', 'Conversation Starter')

def ex_executive_dashboard__summary_parent_company():
    from app.services.extractors import executive_dashboard as ed
    return [' · '.join(ed._parents(row, name)[0]) for row, name in (
        ({'Business Id': 'b', 'Ultimate Parent Id': 's', 'Ultimate Parent Name': 'sm investments'}, 'BANCO DE ORO UNIBANK, INC. (BDO) - PH'),
        ({'Business Id': 'sm', 'Ultimate Parent Id': 'sm', 'Ultimate Parent Name': 'san miguel', 'Parent Company Name': 'top frontier investment holdings'}, 'SAN MIGUEL CORPORATION - PH'),
        ({'Business Id': 'c', 'Ultimate Parent Id': 'x', 'Ultimate Parent Name': 'canon'}, 'CANON INC. - JP'),
        ({'Business Id': 'm', 'Ultimate Parent Id': 'u', 'Ultimate Parent Name': 'us bancorp'}, 'MITSUBISHI UFJ FINANCIAL GROUP, INC. - JP'))]

def ex_executive_dashboard__summary_subsidiaries():
    from app.services.extractors import executive_dashboard as ed
    return ed._subsidiaries([{'Subsidiary Name': n} for n in ('woolworths', 'Big W', 'big w', '', 'endeavour group', 'wesfarmers')], 'WOOLWORTHS GROUP LIMITED - AU', 'wesfarmers')

def ex_executive_dashboard__summary_description_bullets():
    from app.services.extractors import executive_dashboard as ed
    return ed._description_points(None, 'acct', 'Acme makes cement in Indonesia.', {})

def ex_executive_dashboard__filings_on_record():
    from datetime import date

    from app.services.dashboard import filings_register as fr
    return (lambda r: (r['in_window'], r['total_on_record'], r['excluded'], [f['title'] for f in r['filings']]))(fr.register([{'document_title': 'Annual Report 2025', 'publication_date': '2026-03-20', 'document_url': 'https://acme.com/ar2025.pdf', 'download_status': 'DOWNLOADED'}, {'document_title': 'Annual Report 2025 (copy)', 'publication_date': '2026-03-21', 'source_page_url': 'https://www.acme.com/ar2025.pdf'}, {'document_title': 'Annual Report 2023', 'publication_date': '2024-03-20', 'document_url': 'https://acme.com/ar2023.pdf'}, {'document_title': 'Notice', 'publication_date': '', 'document_url': 'https://acme.com/n.pdf'}, {'document_title': 'Half-year', 'publication_date': '11/08/2026', 'document_url': ''}, {'document_title': '8-K', 'publication_date': '1756684800', 'document_url': 'https://sec.gov/x', 'crawl_route': 'PREDICTLEADS_SEC_FILINGS'}], date(2026, 10, 5)))

def ex_executive_dashboard__reported_financials():
    from app.services.dashboard import filings_financials as ff
    return [(c['metric'], c['value_text'], c['period'], c.get('change_text')) for c in ff.reported_metrics([{'company': 'Acme', 'file': 'AR2025.pdf', 'document_title': 'Annual Report 2025', 'period_type': 'FY', 'period_end': '2025-12-31', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '1200', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'revenue_page': '14', 'revenue_prior': '1000', 'revenue_prior_period_end': '2024-12-31', 'net_income': '90', 'net_income_check': 'unverified', 'net_income_scope': 'consolidated', 'net_income_currency': 'USD', 'net_income_scale': 'million', 'employees': '5200', 'employees_check': 'verified', 'employees_scope': 'consolidated', 'ceo_check': 'verified', 'ceo_name': 'Jane Doe', 'ceo_title': 'President Director', 'ceo_page': '5'}, {'company': 'Acme', 'file': 'AR2024.pdf', 'document_title': 'Annual Report 2024', 'period_type': 'FY', 'period_end': '2024-12-31', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '1000', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'net_income': '80', 'net_income_check': 'verified', 'net_income_scope': 'consolidated', 'net_income_currency': 'USD', 'net_income_scale': 'million', 'net_income_page': '20'}, {'company': 'Acme', 'file': 'Q2-2026.pdf', 'period_type': '1H', 'period_end': '2026-06-30', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '700', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'revenue_prior': '600', 'revenue_prior_period_end': '2025-06-30', 'revenue_page': '3'}])]

def ex_executive_dashboard__financials_usable():
    from app.services.dashboard import filings_financials as ff
    return ff._usable({'net_income': '90', 'net_income_check': 'unverified', 'net_income_scope': 'consolidated', 'entity_match': 'same', 'period_end': '2025-12-31'}, 'net_income')

def ex_executive_dashboard__financials_growth():
    from app.services.dashboard import filings_financials as ff
    return [c.get('change_text') for c in ff.reported_metrics([{'company': 'Acme', 'file': 'AR2025.pdf', 'document_title': 'Annual Report 2025', 'period_type': 'FY', 'period_end': '2025-12-31', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '1200', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'revenue_page': '14', 'revenue_prior': '1000', 'revenue_prior_period_end': '2024-12-31', 'net_income': '90', 'net_income_check': 'unverified', 'net_income_scope': 'consolidated', 'net_income_currency': 'USD', 'net_income_scale': 'million', 'employees': '5200', 'employees_check': 'verified', 'employees_scope': 'consolidated', 'ceo_check': 'verified', 'ceo_name': 'Jane Doe', 'ceo_title': 'President Director', 'ceo_page': '5'}, {'company': 'Acme', 'file': 'AR2024.pdf', 'document_title': 'Annual Report 2024', 'period_type': 'FY', 'period_end': '2024-12-31', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '1000', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'net_income': '80', 'net_income_check': 'verified', 'net_income_scope': 'consolidated', 'net_income_currency': 'USD', 'net_income_scale': 'million', 'net_income_page': '20'}, {'company': 'Acme', 'file': 'Q2-2026.pdf', 'period_type': '1H', 'period_end': '2026-06-30', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '700', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'revenue_prior': '600', 'revenue_prior_period_end': '2025-06-30', 'revenue_page': '3'}])][0]

def ex_executive_dashboard__financials_series_display():
    from app.services.dashboard import filings_financials as ff
    return ff._display(250000, {'revenue_scale': 'thousand', 'revenue_currency': 'IDR'}, 'revenue')

def ex_executive_dashboard__ceo():
    from app.services.dashboard import filings_financials as ff
    return ff.ceo([{'company': 'Acme', 'file': 'AR2025.pdf', 'document_title': 'Annual Report 2025', 'period_type': 'FY', 'period_end': '2025-12-31', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '1200', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'revenue_page': '14', 'revenue_prior': '1000', 'revenue_prior_period_end': '2024-12-31', 'net_income': '90', 'net_income_check': 'unverified', 'net_income_scope': 'consolidated', 'net_income_currency': 'USD', 'net_income_scale': 'million', 'employees': '5200', 'employees_check': 'verified', 'employees_scope': 'consolidated', 'ceo_check': 'verified', 'ceo_name': 'Jane Doe', 'ceo_title': 'President Director', 'ceo_page': '5'}, {'company': 'Acme', 'file': 'AR2024.pdf', 'document_title': 'Annual Report 2024', 'period_type': 'FY', 'period_end': '2024-12-31', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '1000', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'net_income': '80', 'net_income_check': 'verified', 'net_income_scope': 'consolidated', 'net_income_currency': 'USD', 'net_income_scale': 'million', 'net_income_page': '20'}, {'company': 'Acme', 'file': 'Q2-2026.pdf', 'period_type': '1H', 'period_end': '2026-06-30', 'entity_match': 'same', 'filing_entity': 'Acme Corp', 'revenue': '700', 'revenue_check': 'verified', 'revenue_scope': 'consolidated', 'revenue_currency': 'USD', 'revenue_scale': 'million', 'revenue_prior': '600', 'revenue_prior_period_end': '2025-06-30', 'revenue_page': '3'}])

def ex_executive_dashboard__exec_hiring_velocity():
    from app.services.hp import hiring_jobs as hj
    return (lambda s: (len(s.jobs), [j['title'] for j in s.jobs], s.basis()))(hj.select_jobs('ACME SDN BHD - MY', [{'company_name': 'ACME SDN BHD - MY', 'account_country_code': 'MY', 'location': 'Kuala Lumpur, Malaysia', 'first_seen_at': '2026-03-01', 'title': 'Data Engineer'}, {'company_name': 'ACME SDN BHD - MY', 'account_country_code': 'MY', 'location': 'Singapore', 'first_seen_at': '2026-04-01', 'title': 'Sales Lead'}, {'company_name': 'ACME SDN BHD - MY', 'account_country_code': 'MY', 'location': '', 'first_seen_at': '2026-05-01', 'title': 'IT Support'}, {'company_name': 'ACME SDN BHD - MY', 'account_country_code': 'MY', 'location': 'Remote', 'first_seen_at': '2025-08-01', 'title': 'Accountant'}, {'company_name': 'ACME SDN BHD - MY', 'account_country_code': 'MY', 'location': 'Penang, Malaysia', 'first_seen_at': '', 'title': 'Technician'}]))

def ex_executive_dashboard__hiring_country_check():
    from app.services.hp import hiring_jobs as hj
    return [hj.location_in_country(l, 'KR') for l in ['Seoul, South Korea', 'Pyongyang, North Korea', 'Columbus, OH', '', 'Tokyo, Japan']]

def ex_executive_dashboard__hiring_window():
    from app.services.hp import hiring_jobs as hj
    return hj.window_start().isoformat()

def ex_executive_dashboard__urgency_score():
    from datetime import date

    from app.services.dashboard import urgency as u
    return {k: v for k, v in u.score([u.workplace_os(['Linux', 'Microsoft Windows OS', 'Apple iOS', 'Microsoft Teams', 'VMware'], '10001+'), u.ai_workstation([(t, 50) for t in ['artificial intelligence', 'machine learning', 'generative ai', 'openai', 'ai strategy', 'ai data analytics', 'ai automation', 'ai/ml operationalization', 'vector database', 'azure for ml', 'ai data management', 'in-database machine learning', 'ai chips', 'model training', 'deep learning', 'computer vision']], ['PyTorch', 'Keras', 'scikit-learn', 'Apache Spark MLlib'], 2, [{'event_date': '2026-08-01', 'event_headline': 'Astra reports quarterly results'}], date(2026, 9, 1)), u.growth_expansion([{'date': '2025-07-31', 'associated_members': 14217}, {'date': '2026-06-30', 'associated_members': 16781}], [{'status': 'closed', 'posted_at': '2026-03-01'}] * 60 + [{'status': '', 'posted_at': '2026-03-01'}] * 40, [{'event_date': '2026-02-01', 'event_headline': 'Astra plans IDR 36 trillion capex for capacity expansion'}], date(2026, 9, 1)), u.hp_solution_intent([{'name': '3D Printers', 'score': 34, 'trend_label': 'Increasing', 'stage': 'Awareness', 'research_volume': 'High', 'keywords': []}])], date(2026, 9, 1)).items() if k in ('score', 'exact_score', 'weighted_contributions', 'coverage_percent', 'publishable')}

def ex_executive_dashboard__urgency_coverage_gate():
    from datetime import date

    from app.services.dashboard import urgency as u
    return {k: v for k, v in u.score([u.workplace_os([], '1001-5000'), u.growth_expansion([], [{'status': 'open', 'posted_at': '2026-05-01'}] * 25, [], date(2026, 10, 5))], date(2026, 10, 5)).items() if k in ('score', 'withheld_score', 'coverage_percent', 'publishable')}

def ex_executive_dashboard__urgency_explanation():
    from app.services.dashboard import urgency as u
    return u.workplace_os(['Windows 11', 'Microsoft Intune'], '1001-5000')['rationale_lines']

def ex_executive_dashboard__driver_workplace_os():
    from app.services.dashboard import urgency as u
    return u.workplace_os(['Linux', 'Microsoft Windows OS', 'Apple iOS', 'Microsoft Teams', 'VMware'], '10001+')['value']

def ex_executive_dashboard__wos_account_scale():
    from app.services.dashboard import urgency as u
    return [u._employee_band_points(x)[0] for x in ['50,000+', '10001+', '5001-10000', '1001-5000', '201-500', '11-50', '10001-50000', '']]

def ex_executive_dashboard__wos_os_environment():
    from app.services.dashboard import urgency as u
    return u.workplace_os(['Linux', 'Microsoft Windows OS', 'Apple iOS'], '')['terms'][1]['points']

def ex_executive_dashboard__wos_footprint():
    from app.services.dashboard import urgency as u
    return u.workplace_os(['VMware vSphere', 'Microsoft Intune'], '')['terms'][2]['points']

def ex_executive_dashboard__driver_ai_workstation():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.ai_workstation([('Artificial Intelligence', 60), ('Machine Learning', 40), ('HTML5', 70), ('Vector Database', 30)], ['TensorFlow', 'Salesforce'], 26, [{'event_date': '2026-06-10', 'event_headline': 'Acme opens AI centre of excellence in Jakarta'}, {'event_date': '2026-06-11', 'event_headline': 'Acme opens AI centre of excellence in Jakarta'}, {'event_date': '2026-07-01', 'event_headline': 'Acme upgrades ERP system'}], date(2026, 10, 5))['value']

def ex_executive_dashboard__ai_breadth():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.ai_workstation([(t, 50) for t in ['artificial intelligence', 'machine learning', 'generative ai', 'openai', 'ai strategy', 'ai data analytics', 'ai automation', 'ai/ml operationalization', 'vector database', 'azure for ml', 'ai data management', 'in-database machine learning', 'ai chips', 'model training', 'deep learning', 'computer vision']], ['PyTorch', 'Keras', 'scikit-learn', 'Apache Spark MLlib'], 2, [], date(2026, 9, 1))['terms'][0]['points']

def ex_executive_dashboard__ai_depth():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.ai_workstation([(t, 50) for t in ['artificial intelligence', 'machine learning', 'generative ai', 'openai', 'ai strategy', 'ai data analytics', 'ai automation', 'ai/ml operationalization', 'vector database', 'azure for ml', 'ai data management', 'in-database machine learning', 'ai chips', 'model training', 'deep learning', 'computer vision']], ['PyTorch', 'Keras', 'scikit-learn', 'Apache Spark MLlib'], 2, [], date(2026, 9, 1))['terms'][1]['points']

def ex_executive_dashboard__ai_workstation_intent():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.ai_workstation([], [], 2, [], date(2026, 9, 1))['terms'][2]['points']

def ex_executive_dashboard__ai_recent_events():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.ai_workstation([], [], None, [{'event_date': '2026-06-10', 'event_headline': 'Acme opens AI centre of excellence in Jakarta'}, {'event_date': '2026-06-11', 'event_headline': 'Acme opens AI centre of excellence in Jakarta'}, {'event_date': '2026-07-01', 'event_headline': 'Acme upgrades ERP system'}], date(2026, 10, 5))['terms'][3]['points']

def ex_executive_dashboard__driver_growth_expansion():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.growth_expansion([{'date': '2025-10-01', 'associated_members': 1000}, {'date': '2026-09-01', 'associated_members': 1035}], [{'status': 'open', 'posted_at': '2026-05-01'}] * 30 + [{'status': '', 'posted_at': '', 'first_seen_at': '2026-01-15'}] * 5 + [{'status': 'closed', 'posted_at': '2024-01-01'}] * 10, [{'event_date': '2026-03-01', 'event_headline': 'Acme opens new plant in Vietnam'}, {'event_date': '2026-04-01', 'event_headline': 'Acme acquires local distributor'}, {'event_date': '2026-05-01', 'event_headline': 'Acme wins award for best employer'}], date(2026, 10, 5))['value']

def ex_executive_dashboard__growth_workforce():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.growth_expansion([{'date': '2025-07-31', 'associated_members': 14217}, {'date': '2026-06-30', 'associated_members': 16781}], [], [], date(2026, 9, 1))['terms'][0]['points']

def ex_executive_dashboard__growth_hiring_volume():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.growth_expansion([], [{'status': 'closed', 'posted_at': '2026-03-01'}] * 60 + [{'status': '', 'posted_at': '2026-03-01'}] * 40, [], date(2026, 9, 1))['terms'][1]['points']

def ex_executive_dashboard__growth_events():
    from datetime import date

    from app.services.dashboard import urgency as u
    return u.growth_expansion([], [], [{'event_date': '2026-03-01', 'event_headline': 'Acme opens new plant in Vietnam'}, {'event_date': '2026-04-01', 'event_headline': 'Acme acquires local distributor'}, {'event_date': '2026-05-01', 'event_headline': 'Acme wins award for best employer'}], date(2026, 10, 5))['terms'][2]['points']

def ex_executive_dashboard__driver_hp_solution_intent():

    from app.services.dashboard import urgency as u
    return u.hp_solution_intent([{'name': 'PCs', 'score': 45, 'trend_label': 'Stable', 'stage': 'Decision/Purchase', 'research_volume': 'Medium'}, {'name': 'Printers', 'score': 30, 'trend_label': 'Increasing', 'stage': 'Awareness', 'research_volume': 'High'}])['value']

def ex_executive_dashboard__hpi_strength():

    from app.services.dashboard import urgency as u
    return u.hp_solution_intent([{'name': '3D Printers', 'score': 34, 'trend_label': 'Increasing', 'stage': 'Awareness', 'research_volume': 'High'}])['terms'][0]['points']

def ex_executive_dashboard__hpi_trend():

    from app.services.dashboard import urgency as u
    return u.hp_solution_intent([{'name': '3D Printers', 'score': 34, 'trend_label': 'Increasing', 'stage': 'Awareness', 'research_volume': 'High'}])['terms'][1]['points']

def ex_executive_dashboard__hpi_stage():

    from app.services.dashboard import urgency as u
    return u.hp_solution_intent([{'name': '3D Printers', 'score': 34, 'trend_label': 'Increasing', 'stage': 'Awareness', 'research_volume': 'High'}])['terms'][2]['points']

def ex_executive_dashboard__hpi_volume():

    from app.services.dashboard import urgency as u
    return u.hp_solution_intent([{'name': '3D Printers', 'score': 34, 'trend_label': 'Increasing', 'stage': 'Awareness', 'research_volume': 'High'}])['terms'][3]['points']

def ex_executive_dashboard__priority_relevance_gate():
    from app.services.dashboard import priorities as pr
    return [pr._supports({'source_text': 'We are investing in sustainable manufacturing.'}, pr._content_words('Strengthen sustainability initiatives')), pr._supports({'source_text': 'Profit optimisation in Document Solutions.'}, pr._content_words('Strengthen sustainability initiatives'))]

def ex_executive_dashboard__priority_dedup():
    from app.services.dashboard import priorities as pr
    return [p['title'] for p in pr._distinct([{'title': 'Expand data centre capacity'}, {'title': 'Expand data centre capacity in Indonesia'}, {'title': 'Scale AI across operations'}])[0]]

def ex_executive_dashboard__evidence_strength():
    from datetime import date

    from app.services.dashboard import evidence_strength as es
    return es.score([{'filing_label': 'Acme Annual Report 2025', 'period': 'FY2025', 'dataset': 'compliance_filings'}, {'filing_label': 'Acme Annual Report 2025', 'period': 'FY2025', 'dataset': 'compliance_filings'}, {'filing_label': 'Acme Q2 2026 Report', 'period': '2026-Jun', 'dataset': 'compliance_filings'}, {'source_url': 'https://www.reuters.com/x', 'period': '2026-08-20', 'dataset': 'google_news'}, {'source_url': 'https://news.google.com/rss/abc', 'publisher': 'Jakarta Post', 'dataset': 'google_news'}, {'source_url': 'https://acme.co.id/news/1', 'dataset': 'google_news'}], date(2026, 10, 5), 'acme.com')['score']

def ex_executive_dashboard__es_filing():

    from app.services.dashboard import evidence_strength as es
    return es.filing_evidence([{'filing_label': 'Acme Annual Report 2025', 'period': 'FY2025', 'dataset': 'compliance_filings'}, {'filing_label': 'Acme Annual Report 2025', 'period': 'FY2025', 'dataset': 'compliance_filings'}, {'filing_label': 'Acme Q2 2026 Report', 'period': '2026-Jun', 'dataset': 'compliance_filings'}, {'source_url': 'https://www.reuters.com/x', 'period': '2026-08-20', 'dataset': 'google_news'}, {'source_url': 'https://news.google.com/rss/abc', 'publisher': 'Jakarta Post', 'dataset': 'google_news'}, {'source_url': 'https://acme.co.id/news/1', 'dataset': 'google_news'}])['points']

def ex_executive_dashboard__es_recency():
    from datetime import date

    from app.services.dashboard import evidence_strength as es
    return [es.recency([{'period': p}], date(2026, 10, 5))['points'] for p in ['2026-09-01', '2025-Sep', 'FY2024', 'FY2022', 'FY2020', '2019-01-01', 'Q3 2025']]

def ex_executive_dashboard__es_diversity():

    from app.services.dashboard import evidence_strength as es
    return [es.categorise(s, 'astra.co.id') for s in [{'source_url': 'https://www.idx.co.id/x'}, {'source_url': 'https://www.gov.uk/x'}, {'source_url': 'https://ir.astra.co.id/x'}, {'source_url': 'https://careers.astra.com/x'}, {'source_url': 'https://www.linkedin.com/x'}, {'source_url': 'https://news.google.com/x', 'publisher': 'Kompas'}, {'publisher': 'Astra', 'company_name': 'Astra'}, {}]]

def ex_executive_dashboard__catalyst_description():
    from app.services.dashboard import priorities as pr
    return [pr._validate_description(b, 'Acme plans a 30 MW data centre in Batam', 'HP Z Workstations: for AI') for b in ['Acme is building a 40 MW data centre in Batam. HP Z Workstations fit this.', 'Acme is building a 30 MW data centre in Batam. HP Poly devices fit.', 'The company is building a data centre.', 'Acme is building a 30 MW data centre in Batam. HP Z Workstations fit this.']]

def ex_executive_dashboard__claim_points():
    from app.services.dashboard import priorities as pr
    return pr.claim_point('Acme Group operates in six segments. In 2025, the Company expanded its data centre capacity in Batam to support cloud customers, which required new cooling systems and additional power. Revenue grew.', pr._content_words('Expand data centre capacity'))

def ex_executive_dashboard__executive_summary_text():
    from app.services.dashboard import priorities as pr
    return pr._executive_summary('Acme', [{'title': 'Expand data centre capacity', 'measures': {'support_count': 5, 'distinct_sections': 3, 'most_recent_date': 'FY2025'}, 'sources': [{'evidence_id': 'e1'}, {'evidence_id': 'e2'}]}, {'title': 'Scale AI', 'measures': {'support_count': 3, 'distinct_sections': 2, 'most_recent_date': '2026-08-01'}, 'sources': [{'evidence_id': 'e3'}]}], [{'metric': 'Net Revenue', 'value_text': 'USD 1,200 million', 'period': 'FY2025', 'evidence_id': 'm1'}])['sentences']

def ex_intent_demand_signals__int_lead_source():
    from app.services.extractors import intent_demand_signals as ids
    topics, _ = ids._build_topics([{'Topic': 'Laptops', 'Composite Score': '80'}, {'Topic': 'Personal Computer: 2-in-1 PCs', 'Composite Score': '65'}, {'Topic': 'Workstations', 'Composite Score': '89'}, {'Topic': 'Cloud: Kubernetes', 'Composite Score': '92'}])
    return ids._bu_summary(topics, [], {'laptops': {'category': 'PC', 'reason': 'laptops'}, 'personal computer: 2-in-1 pcs': {'category': 'PC', 'reason': '2-in-1'}, 'workstations': {'category': 'Workstation', 'reason': 'ws'}, 'cloud: kubernetes': {'category': 'none', 'reason': 'cloud'}})['lead_source']

def ex_intent_demand_signals__int_domain_match():
    from app.services.extractors import intent_demand_signals as ids
    return [[m['status'], m['matched_by']] for m in (
        ids._match_provider_account([{'Company Website': w, 'Company Name': 'x', 'Date Stamp': '20260901'}], d)[0]
        for w, d in (('nsw.gov.au', 'health.nsw.gov.au'), ('https://www.iag.com.au', 'iag.co.nz'), ('acme-holdings.com', 'astra.co.id')))]

def ex_intent_demand_signals__int_topics_table():
    from app.services.extractors import intent_demand_signals as ids
    t, d = ids._build_topics([{'Topic': 'Laptops', 'Composite Score': '72'}, {'Topic': 'laptops', 'Composite Score': '90'}, {'Topic': '3D Printing', 'Composite Score': '88'}, {'Topic': 'Zero Trust', 'Composite Score': 'n/a'}])
    return ([(x['topic_name'], x['composite_score'], x['included'], x['intensity'], x['theme'], x['hp_category']) for x in t], d)

def ex_intent_demand_signals__int_topic_dedup_exclusion():
    from app.services.extractors import intent_demand_signals as ids
    return ids._build_topics([{'Topic': 'Zero Trust', 'Composite Score': 'n/a'}])[0][0]['exclusion_reason']

def ex_intent_demand_signals__int_intensity():
    from app.services.hp import intent_topic_map as tm
    return (tm.intensity(85), tm.intensity(84), tm.intensity(70), tm.intensity(69))

def ex_intent_demand_signals__int_dictionary_mapping():
    from app.services.hp import intent_topic_map as tm
    return [(s, tm.map_topic(s)['theme'], tm.map_topic(s)['hp_category']) for s in ['3D Printing', 'Managed Print Services', 'Meeting Room Solutions', 'Quantum Computing']]

def ex_intent_demand_signals__int_mapping_conflicts():
    from app.services.hp import intent_topic_map as tm
    return [(s, tm.map_topic(s)['theme'], tm.map_topic(s)['hp_category'], tm.map_topic(s)['mapping_status']) for s in ['security: cloud security', 'Laptops and Workstations', 'Print Advertising']]

def ex_intent_demand_signals__int_hiring_linked_tag():
    from app.services.hp import intent_topic_map as tm
    return (tm.is_hiring_linked('Talent Acquisition'), tm.is_hiring_linked('hr tech: successfactors'))

def ex_intent_demand_signals__int_theme_stats():
    from app.services.extractors import intent_demand_signals as ids
    topics, _ = ids._build_topics([{'Topic': 'Laptops', 'Composite Score': '80'}, {'Topic': 'Personal Computer: 2-in-1 PCs', 'Composite Score': '65'}, {'Topic': 'Workstations', 'Composite Score': '89'}, {'Topic': 'Cloud: Kubernetes', 'Composite Score': '92'}])
    s = ids._summarise(topics, {'status': 'no_file', 'categories': {}}, [])
    return [(t['theme'], t['topic_count'], t['max'], t['average']) for t in s['themes'] if t['topic_count']]

def ex_intent_demand_signals__int_category_file():
    from app.services.extractors import intent_demand_signals as ids
    cf = ids._parse_category_file([['', '', '', '', 'PCs (Score /100)', '', '', 'Workstations (Score /100)', '', ''], ['company', 'domain', 'run date', 'top hp category', 'intent score (/100)', 'buying stage', 'topics researched', 'intent score (/100)', 'buying stage', 'topics researched'], ['Astra', 'astra.co.id', '2026-08-01', 'Workstations', '35', 'Consideration', 'Laptops | Windows 11', '40', 'Awareness', 'CAD'], ['Astra', 'astra.co.id', '2026-09-01', 'Workstations', '32', 'Consideration', 'Laptops | Windows 11', '38', 'No Signal', '-'], ['Other', 'other.com', '2026-09-01', 'PCs', '50', 'Decision', 'x', '0', 'No Signal', '-']], 'astra.co.id')
    return (cf['status'], cf['source']['run_date'], cf['source']['runs_on_file'], {k: (v['score'], v['stage'], v['has_signal']) for k, v in cf['categories'].items()})

def ex_intent_demand_signals__int_has_signal():
    from app.services.extractors import intent_demand_signals as ids
    return ids._parse_category_file([['', '', '', '', 'PCs (Score /100)', '', '', 'Workstations (Score /100)', '', ''], ['company', 'domain', 'run date', 'top hp category', 'intent score (/100)', 'buying stage', 'topics researched', 'intent score (/100)', 'buying stage', 'topics researched'], ['Astra', 'astra.co.id', '2026-08-01', 'Workstations', '35', 'Consideration', 'Laptops | Windows 11', '40', 'Awareness', 'CAD'], ['Astra', 'astra.co.id', '2026-09-01', 'Workstations', '32', 'Consideration', 'Laptops | Windows 11', '38', 'No Signal', '-'], ['Other', 'other.com', '2026-09-01', 'PCs', '50', 'Decision', 'x', '0', 'No Signal', '-']], 'astra.co.id')['categories']['Workstation']['has_signal']

def ex_intent_demand_signals__int_trend_and_flags():
    from app.services.extractors import intent_demand_signals as ids
    return ids._parse_category_file([['', '', '', '', 'PCs (Score /100)', '', '', 'Workstations (Score /100)', '', ''], ['company', 'domain', 'run date', 'top hp category', 'intent score (/100)', 'buying stage', 'topics researched', 'intent score (/100)', 'buying stage', 'topics researched'], ['Astra', 'astra.co.id', '2026-08-01', 'Workstations', '35', 'Consideration', 'Laptops | Windows 11', '40', 'Awareness', 'CAD'], ['Astra', 'astra.co.id', '2026-09-01', 'Workstations', '32', 'Consideration', 'Laptops | Windows 11', '38', 'No Signal', '-'], ['Other', 'other.com', '2026-09-01', 'PCs', '50', 'Decision', 'x', '0', 'No Signal', '-']], 'astra.co.id')['categories']['PC']['quality_flags']

def ex_intent_demand_signals__int_top_check():
    from app.services.extractors import intent_demand_signals as ids
    return ids._parse_category_file([['', '', '', '', 'PCs (Score /100)', '', '', 'Workstations (Score /100)', '', ''], ['company', 'domain', 'run date', 'top hp category', 'intent score (/100)', 'buying stage', 'topics researched', 'intent score (/100)', 'buying stage', 'topics researched'], ['Astra', 'astra.co.id', '2026-08-01', 'Workstations', '35', 'Consideration', 'Laptops | Windows 11', '40', 'Awareness', 'CAD'], ['Astra', 'astra.co.id', '2026-09-01', 'Workstations', '32', 'Consideration', 'Laptops | Windows 11', '38', 'No Signal', '-'], ['Other', 'other.com', '2026-09-01', 'PCs', '50', 'Decision', 'x', '0', 'No Signal', '-']], 'astra.co.id')['top_check']['consistent']

def ex_intent_demand_signals__int_supporting_signals():
    from app.services.extractors import intent_demand_signals as ids
    inv = ids._tech_inventory([{'Product And Design': 'AutoCAD, SolidWorks', 'Full Tech Stack': 'AutoCAD, NVIDIA, Microsoft Intune', 'It Management': 'Microsoft Intune'}], [{'Technologies Used By Company Website': 'Google Analytics, Zoom'}])
    return [(s['signal'], s['max'], s['confirmed'], [t['name'] for t in s['technologies']]) for s in ids._supporting_signals([{'topic_name': 'CAD Software', 'composite_score': 81}, {'topic_name': 'GPU', 'composite_score': 77}, {'topic_name': 'Data Analytics', 'composite_score': 90}], 'Workstation', inv)]

def ex_intent_demand_signals__int_tech_inventory():
    from app.services.extractors import intent_demand_signals as ids
    return [(x['name'], x['column']) for x in ids._tech_inventory([{'Product And Design': 'AutoCAD, SolidWorks', 'Full Tech Stack': 'AutoCAD, NVIDIA, Microsoft Intune', 'It Management': 'Microsoft Intune'}], [{'Technologies Used By Company Website': 'Google Analytics, Zoom'}])]

def ex_intent_demand_signals__int_category_explanation():
    from app.services.extractors import intent_demand_signals as ids
    inv = ids._tech_inventory([{'Product And Design': 'AutoCAD, SolidWorks', 'Full Tech Stack': 'AutoCAD, NVIDIA, Microsoft Intune', 'It Management': 'Microsoft Intune'}], [{'Technologies Used By Company Website': 'Google Analytics, Zoom'}])
    return ids._category_explanation({'category': 'Workstation', 'hp_play': 'Z by HP Workstations'}, {'score': 38, 'stage': 'Awareness'}, ids._supporting_signals([{'topic_name': 'CAD Software', 'composite_score': 81}, {'topic_name': 'GPU', 'composite_score': 77}, {'topic_name': 'Data Analytics', 'composite_score': 90}], 'Workstation', inv))

def ex_intent_demand_signals__int_evidence_tier():
    from app.services.extractors import intent_demand_signals as ids
    inv = ids._tech_inventory([{'Product And Design': 'AutoCAD, SolidWorks', 'Full Tech Stack': 'AutoCAD, NVIDIA, Microsoft Intune', 'It Management': 'Microsoft Intune'}], [{'Technologies Used By Company Website': 'Google Analytics, Zoom'}])
    sig = ids._supporting_signals([{'topic_name': 'CAD Software', 'composite_score': 81}, {'topic_name': 'GPU', 'composite_score': 77}, {'topic_name': 'Data Analytics', 'composite_score': 90}], 'Workstation', inv)
    return (ids._category_tier({'primary': {'score': 38, 'has_signal': True}, 'supporting_signals': sig})['tier'], ids._category_tier({'primary': {'score': 0, 'has_signal': False}, 'supporting_signals': sig})['tier'])

def ex_intent_demand_signals__int_so_what_category():
    from app.services.extractors import intent_demand_signals as ids
    return ids._closer_to_band(' '.join(['w'] * 84), ' '.join(['w'] * 40))

def ex_intent_demand_signals__int_tier_wording_guard():
    from app.services.hp.guardrails import tier_language_faults
    return tier_language_faults('Astra needs new workstations for its engineers.', 'Conversation Starter')

def ex_intent_demand_signals__int_so_what_box():
    from app.services.extractors import intent_demand_signals as ids
    return ids._summarise([], {'status': 'matched', 'categories': {'PC': {'score': 32, 'stage': 'Consideration', 'has_signal': True, 'quality_flags': []}, 'Workstation': {'score': 0, 'stage': 'No Signal', 'has_signal': False, 'quality_flags': []}}}, [])['so_what']

def ex_intent_demand_signals__int_bu_summary():
    from app.services.extractors import intent_demand_signals as ids
    bu = ids._bu_summary([], [{'category': 'PC', 'primary': {'score': 32, 'stage': 'Consideration'}}, {'category': 'Workstation', 'primary': {'score': 38, 'stage': 'Awareness'}}], None)
    return (bu['lead_source'], [(u['category'], u['score'], u['score_basis']) for u in bu['units']])

def ex_intent_demand_signals__int_bu_average():
    from app.services.extractors import intent_demand_signals as ids
    topics, _ = ids._build_topics([{'Topic': 'Laptops', 'Composite Score': '80'}, {'Topic': 'Personal Computer: 2-in-1 PCs', 'Composite Score': '65'}, {'Topic': 'Workstations', 'Composite Score': '89'}, {'Topic': 'Cloud: Kubernetes', 'Composite Score': '92'}])
    bu = ids._bu_summary(topics, [], {'laptops': {'category': 'PC', 'reason': 'laptops'}, 'personal computer: 2-in-1 pcs': {'category': 'PC', 'reason': '2-in-1'}, 'workstations': {'category': 'Workstation', 'reason': 'ws'}, 'cloud: kubernetes': {'category': 'none', 'reason': 'cloud'}})
    return ([(u['category'], u['score'], u['bombora_topic_count'], u['bombora_score_sum']) for u in bu['units']], bu['long_tail'])

def ex_intent_demand_signals__int_bu_fallback():
    from app.services.extractors import intent_demand_signals as ids
    topics, _ = ids._build_topics([{'Topic': 'Laptops', 'Composite Score': '80'}, {'Topic': 'Personal Computer: 2-in-1 PCs', 'Composite Score': '65'}, {'Topic': 'Workstations', 'Composite Score': '89'}, {'Topic': 'Cloud: Kubernetes', 'Composite Score': '92'}])
    labels = {k: {'category': 'none', 'reason': 'r'} for k in {'laptops': {'category': 'PC', 'reason': 'laptops'}, 'personal computer: 2-in-1 pcs': {'category': 'PC', 'reason': '2-in-1'}, 'workstations': {'category': 'Workstation', 'reason': 'ws'}, 'cloud: kubernetes': {'category': 'none', 'reason': 'cloud'}}}
    bu = ids._bu_summary(topics, [{'category': 'PC', 'primary': {'score': 32, 'stage': 'Consideration'}}, {'category': 'Workstation', 'primary': {'score': 38, 'stage': 'Awareness'}}], labels)
    return (bu['score_source'], [(u['category'], u['score']) for u in bu['units']][:2], len(bu['long_tail']))

def ex_intent_demand_signals__int_bu_reads():
    from app.services.extractors import intent_demand_signals as ids
    return (ids._has_figure('Research into 2-in-1 PCs suggests a device refresh conversation could be worth opening.', ['PC', 'personal computer: 2-in-1 pcs']), ids._has_figure('Across 73 topics the research suggests interest.', ['PC']))

def ex_intent_demand_signals__hire_job_selection():
    from app.services.hp import hiring_jobs as hj
    jobs = [{'location': 'Singapore', 'first_seen_at': '2026-03-01'}, {'location': 'Kuala Lumpur, Malaysia', 'first_seen_at': '2026-03-01'}, {'location': '', 'first_seen_at': '2025-06-01'}, {'location': '', 'first_seen_at': ''}, {'location': 'Penang, Malaysia', 'first_seen_at': '2025-09-18T10:00:00Z'}, {'location': 'Austin, Texas, United States', 'first_seen_at': '2026-05-01'}]
    [r.update({'company_name': 'JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG', 'account_country_code': 'MY; SG'}) for r in jobs]
    sel = hj.select_jobs('JABIL CIRCUIT SDN BHD - MY', jobs)
    return (len(sel.jobs), sel.basis()['dropped_other_country'], sel.basis()['dropped_older_than_window'], sel.basis()['dropped_no_first_seen'])

def ex_intent_demand_signals__hire_country_code():
    from app.services.hp import hiring_jobs as hj
    rows = [{'company_name': 'JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG', 'account_country_code': 'MY; SG'}]
    return (hj.account_country_code('JABIL CIRCUIT (SINGAPORE) PTE LTD - SG', rows), hj.account_country_code('JABIL CIRCUIT SDN BHD - MY', rows))

def ex_intent_demand_signals__hire_country_check():
    from app.services.hp import hiring_jobs as hj
    return (hj.location_in_country('Cremorne, Victoria, Australia', 'AU'), hj.location_in_country('Columbus, OH', 'AU'), hj.location_in_country('Port Moresby, Papua New Guinea', 'AU'), hj.location_in_country('Singapore', 'MY'))

def ex_intent_demand_signals__hire_window():
    from app.services.hp import hiring_jobs as hj
    return hj.window_start().isoformat()

def ex_intent_demand_signals__hire_postings_tile():
    from app.services.extractors import hiring_signals as hs
    s = hs.postings_summary([{'contract_types': '["Hybrid"]', 'first_seen_at': '2026-01-02', 'last_seen_at': '2026-09-01'}, {'contract_types': '["Full time"]', 'first_seen_at': '2025-12-01', 'last_seen_at': '2026-05-01'}, {'contract_types': '["Work From Home", "Contract"]'}])
    return (s['job_postings'], s['hybrid_count'], s['hybrid_pct'], s['seen_from'], s['seen_to'])

def ex_intent_demand_signals__hire_family_breakdown():
    from app.services.extractors import hiring_signals as hs
    fam = [{'onet_data': {'family': f}} for f in ['Management'] * 5 + ['Sales'] * 4 + ['Office'] * 3 + ['Computer'] * 3 + ['Business'] * 2 + ['Production'] * 2 + ['Legal', 'Education']] + [{'onet_data': {}}]
    return [(b['family'], b['count']) for b in hs.family_breakdown(fam)['bars']]

def ex_intent_demand_signals__hire_tech_tags():
    from app.services.extractors import hiring_signals as hs
    t = hs.tech_tags([{'tags': '["SAP", "Power BI", "Internship", "Australia Post", "SAP"]'}, {'tags': '["SAP", "Excel", "Auspost"]'}, {'tags': '["Power BI", "Austr"]'}], hs._own_name_keys('AUSTRALIA POST - AU', 'auspost.com.au'))
    return ([(x['tag'], x['jobs']) for x in t['tags']], t['removed'])

def ex_intent_demand_signals__hire_theme_assignment():
    from app.services.hp import hiring_themes as ht
    return [(c, ht.theme_for(c).name if ht.theme_for(c) else None) for c in ['15-1212.00', '15-2051.00', '11-2021.00', '41-2031.00', '23-2011.00', '']]

def ex_intent_demand_signals__hire_theme_cards():
    from app.services.extractors import hiring_signals as hs
    c = hs.theme_cards([{'onet_data': {'code': '15-1212.00'}, 'title': 'Security Engineer'}, {'onet_data': {'code': '15-1212.00'}, 'title': 'Security Engineer'}, {'onet_data': {'code': '15-1299.05'}, 'title': 'SOC Analyst'}, {'onet_data': {'code': '43-4051.00'}, 'title': 'Customer Service Rep'}, {'onet_data': {'code': '43-4051.00'}, 'title': 'Customer Service Rep'}, {'onet_data': {'code': '43-4051.00'}, 'title': 'Contact Centre Agent'}, {'onet_data': {}, 'title': 'Unknown'}])
    return ([(x['theme'], x['job_count'], [(t['title'], t['posted']) for t in x['titles']], x['more_jobs']) for x in c['cards']], c['unthemed_jobs'])

def ex_message_evaluator__me_scoring():
    return [(o, __import__('app.services.evaluator.scoring', fromlist=['_']).composite({'relevance': 80, 'impact': 70, 'brand_recall': 60, 'clarity': 90, 'creativity': 50, 'emotional_connection': 40, 'next_step_strength': 75}, o)) for o in __import__('app.services.evaluator.scoring', fromlist=['_']).OBJECTIVES]

def ex_message_evaluator__me_score_bands():
    return [__import__('app.services.evaluator.scoring', fromlist=['_']).score_band(x) for x in (90, 89.9, 75, 74, 40, 39, 19, None)]

def ex_message_evaluator__me_dimension_validation():
    return __import__('app.services.evaluator.scoring', fromlist=['_']).pad_missing(*__import__('app.services.evaluator.scoring', fromlist=['_']).validate_dimensions({'relevance': 80, 'impact': '70', 'brand_recall': 400, 'clarity': 'excellent'}, 'awareness'))

def ex_message_evaluator__me_severe_failures():
    return __import__('app.services.evaluator.evaluate', fromlist=['_'])._severe_failures('Hi Budi, Poly Studio bars give finance teams clearer meetings. Could I send you pricing?', 'cfo')

def ex_message_evaluator__me_scoring_context():
    return __import__('app.services.evaluator.evaluate', fromlist=['_'])._hp_lines_named('Our HP Wolf Security and HP Elite / Pro PCs bundle')

def ex_message_evaluator__me_structure_checks():
    return (lambda r: (r['checks_passed'], r['checks_total'], [(c['check'], c['passed']) for c in r['checks']]))(__import__('app.services.evaluator.formats', fromlist=['_']).structure_checks('Subject: Re: your Cikarang plant refresh\n\nDear Ms Tan,\n\nAt HP we noticed your plant expansion. Would you be open to a 20-minute call next week?\n\nBest regards,\nAndi', 'email'))

def ex_message_evaluator__me_claim_verdict():
    return [(c['verdict'], c['routed_to']) for c in [__import__('app.services.evaluator.sources', fromlist=['_']).EvaluatorSources('a1', 'Astra', 'indonesia', __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['4500 employees', 'Cikarang plant']), __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['HP Wolf Security isolates threats in micro-VMs']), {'title': 'CFO', 'name': 'Budi Santoso'}, "We are the world's most secure. HP Wolf Security stops 99% of attacks. Your 4500 staff deserve better.", 1, True).verify_claim(t) for t in ('HP Wolf Security stops 99% of attacks.', 'Your 4500 staff deserve better.', "We are the world's most secure.", 'We help teams.')]]

def ex_message_evaluator__me_phrase_feedback():
    return (lambda r: ([(p['start'], p['end'], p['verdict'], p['color'], p['problem_type']) for p in r[0]], r[1]))(__import__('app.services.evaluator.verify', fromlist=['_']).verify_phrases([{'chunk': "We are the world's most secure.", 'verdict': 'Keep'}, {'chunk': 'HP Wolf Security stops 99% of attacks.', 'verdict': 'Improve'}, {'chunk': 'Your 4500 staff deserve better.', 'verdict': 'Keep'}, {'chunk': 'Something never written', 'verdict': 'Keep'}], __import__('app.services.evaluator.sources', fromlist=['_']).EvaluatorSources('a1', 'Astra', 'indonesia', __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['4500 employees', 'Cikarang plant']), __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['HP Wolf Security isolates threats in micro-VMs']), {'title': 'CFO', 'name': 'Budi Santoso'}, "We are the world's most secure. HP Wolf Security stops 99% of attacks. Your 4500 staff deserve better.", 1, True), 5))

def ex_message_evaluator__me_chunk_fidelity():
    return (lambda s: __import__('app.services.evaluator.verify', fromlist=['_']).chunk_fidelity(__import__('app.services.evaluator.verify', fromlist=['_']).verify_phrases([{'chunk': "We are the world's most secure."}, {'chunk': 'HP Wolf Security stops 99% of attacks.'}], s, 5)[0], s.draft))(__import__('app.services.evaluator.sources', fromlist=['_']).EvaluatorSources('a1', 'Astra', 'indonesia', __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['4500 employees', 'Cikarang plant']), __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['HP Wolf Security isolates threats in micro-VMs']), {'title': 'CFO', 'name': 'Budi Santoso'}, "We are the world's most secure. HP Wolf Security stops 99% of attacks. Your 4500 staff deserve better.", 1, True))

def ex_message_evaluator__me_reaction_guard():
    return [(r[0] is not None, r[1]) for r in [__import__('app.services.evaluator.verify', fromlist=['_']).guard_reaction(t, __import__('app.services.evaluator.sources', fromlist=['_']).EvaluatorSources('a1', 'Astra', 'indonesia', __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['4500 employees', 'Cikarang plant']), __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['HP Wolf Security isolates threats in micro-VMs']), {'title': 'CFO', 'name': 'Budi Santoso'}, "We are the world's most secure. HP Wolf Security stops 99% of attacks. Your 4500 staff deserve better.", 1, True)) for t in ('Budi thinks this is too long.', 'Someone in this role would want the cost case first.', 'He believes "pricing" matters.')]]

def ex_message_evaluator__me_cache_versions():
    return __import__('app.services.evaluator.storage', fromlist=['_']).message_fingerprint('Hello  world', 'cfo', 'awareness', 'email', 'DEEP', 'p%d-pack%d' % (__import__('app.services.evaluator.evaluate', fromlist=['_']).PROMPT_VERSION, __import__('app.services.hp.buyer_personas', fromlist=['_']).PERSONA_PACK_VERSION))[:16]

def ex_message_evaluator__me_rewrite_greeting():
    return [__import__('app.services.evaluator.formats', fromlist=['_'])._short_role(t) for t in ('Head of information technology project procurement', 'Chief Financial Officer', 'VP / Head of Information Technology')]

def ex_message_evaluator__me_rewrite_validation():
    return __import__('app.services.evaluator.formats', fromlist=['_']).validate_rewrite({'rewrite': {'opening': 'x' * 150, 'body_sections': [{'text': 'y' * 150}], 'cta': 'Open to a chat?'}}, 'linkedin_message', (), {'title': 'CFO'}, '')

def ex_message_evaluator__me_rewrite_diff():
    return __import__('app.services.evaluator.verify', fromlist=['_']).diff_rewrite('Your 4500 staff deserve better.', 'Your 4500 staff and 12 sites deserve the best PCs from the market-leading vendor.', __import__('app.services.evaluator.sources', fromlist=['_']).EvaluatorSources('a1', 'Astra', 'indonesia', __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['4500 employees', 'Cikarang plant']), __import__('app.services.extractors.grounding', fromlist=['_']).Corpus(['HP Wolf Security isolates threats in micro-VMs']), {'title': 'CFO', 'name': 'Budi Santoso'}, "We are the world's most secure. HP Wolf Security stops 99% of attacks. Your 4500 staff deserve better.", 1, True), ['tighten'])[1]

def ex_objection_playbook__technology_evidence_source():
    return __import__('app.services.extractors.objection_playbook', fromlist=['_'])._usable([{'a': '', 'b': None}])

def ex_objection_playbook__vendor_token_matching():
    return __import__('app.services.extractors.objection_playbook', fromlist=['_'])._token_present('poly', 'Polycom')

def ex_objection_playbook__area_evidence_string():
    return [a['evidence'] for a in __import__('app.services.extractors.objection_playbook', fromlist=['_'])._build_area_evidence({'Full Tech Stack': 'Dell Latitude, Microsoft Teams, Zoom, Canon imageRUNNER, Kaspersky Endpoint Security, Fortinet FortiGate, Okta, Microsoft Intune, SAP ERP', 'Collaboration': 'Microsoft Teams, Zoom', 'It Security': 'Kaspersky Endpoint Security, Fortinet FortiGate', 'It Management': 'Microsoft Intune'})]

def ex_objection_playbook__topic_owner():
    return [(a, __import__('app.services.extractors.objection_playbook', fromlist=['_'])._resolve_likely_raiser(a, [{'Prospect job_title': 'Head of IT Procurement', 'Prospect job_department_main': 'it'}, {'Prospect job_title': 'Head of Cloud Operations', 'Prospect job_department_main': 'it'}, {'Prospect job_title': 'IT Security Manager', 'Prospect job_department_main': 'it'}, {'Prospect job_title': 'General Affairs Manager', 'Prospect job_department_main': 'operations'}])) for a in __import__('app.services.extractors.objection_playbook', fromlist=['_']).AREA_CATEGORY_COLUMNS]

def ex_objection_playbook__topic_owner_wording():
    return __import__('app.services.extractors.objection_playbook', fromlist=['_'])._resolve_likely_raiser('Collaboration', [{'Prospect job_title': 'Head of Cloud Operations', 'Prospect job_department_main': 'it'}])

def ex_objection_playbook__rulebook_evidence_corpus():
    return __import__('app.services.hp.rulebook', fromlist=['_'])._is_meaningful('company_domain', 'astra.co.id')

def ex_objection_playbook__rule_fired_by():
    return __import__('app.services.hp.rulebook', fromlist=['_'])._fired_by({'routing': [{'opportunity_type': 'Security', 'families': ['WOLF'], 'order': 1, 'signal_tokens': ['endpoint threat'], 'observable_terms': []}], 'rules': [{'rule_label': 'WOLF 09', 'family': 'WOLF', 'part': 'B', 'order': 9, 'offering': 'HP Wolf Pro Security', 'signal_tokens': ['kaspersky', 'symantec endpoint protection'], 'observable_terms': [], 'allowed_facts': ['Wolf Pro Security isolates risky email attachments.'], 'conditions': []}, {'rule_label': 'CARE 03', 'family': 'CARE', 'part': 'B', 'order': 3, 'offering': 'HP Care Pack', 'signal_tokens': ['sap erp'], 'observable_terms': [], 'allowed_facts': ['Next business day onsite support.'], 'conditions': []}, {'rule_label': 'POLY 02', 'family': 'POLY', 'part': 'B', 'order': 2, 'offering': 'Poly Studio', 'signal_tokens': ['meeting rooms'], 'observable_terms': ['microsoft teams rooms'], 'allowed_facts': ['Poly Studio is certified for Microsoft Teams Rooms.'], 'conditions': []}], 'matrices': {}, 'guardrails': [], 'country_lists': {}}['rules'][0], [{'text': 'Kaspersky Endpoint Security'}, {'text': 'SAP ERP'}, {'text': 'Microsoft Teams Rooms'}])

def ex_objection_playbook__qualifying_vs_indicative():
    return __import__('app.services.hp.rulebook', fromlist=['_']).indicative_term('sap erp')

def ex_objection_playbook__family_gates():
    return __import__('app.services.hp.rulebook', fromlist=['_']).iq_availability({'matrices': {}}, 'Indonesia')['available']

def ex_objection_playbook__rule_conditions():
    return __import__('app.services.hp.rulebook', fromlist=['_']).check_conditions({'conditions': [{'condition_type': 'licence', 'text': 'Requires E5 licence'}]}, [], 'Indonesia')

def ex_objection_playbook__area_to_rule_families():
    return (lambda rb, op: (lambda m: {a: [x['rule_label'] for x in m if x['family'] in op._area_families(a)][:op.MAX_RULES_PER_AREA] for a in op.AREA_CATEGORY_COLUMNS})(rb.candidates({'routing': [{'opportunity_type': 'Security', 'families': ['WOLF'], 'order': 1, 'signal_tokens': ['endpoint threat'], 'observable_terms': []}], 'rules': [{'rule_label': 'WOLF 09', 'family': 'WOLF', 'part': 'B', 'order': 9, 'offering': 'HP Wolf Pro Security', 'signal_tokens': ['kaspersky', 'symantec endpoint protection'], 'observable_terms': [], 'allowed_facts': ['Wolf Pro Security isolates risky email attachments.'], 'conditions': []}, {'rule_label': 'CARE 03', 'family': 'CARE', 'part': 'B', 'order': 3, 'offering': 'HP Care Pack', 'signal_tokens': ['sap erp'], 'observable_terms': [], 'allowed_facts': ['Next business day onsite support.'], 'conditions': []}, {'rule_label': 'POLY 02', 'family': 'POLY', 'part': 'B', 'order': 2, 'offering': 'Poly Studio', 'signal_tokens': ['meeting rooms'], 'observable_terms': ['microsoft teams rooms'], 'allowed_facts': ['Poly Studio is certified for Microsoft Teams Rooms.'], 'conditions': []}], 'matrices': {}, 'guardrails': [], 'country_lists': {}}, [{'text': 'Kaspersky Endpoint Security'}, {'text': 'SAP ERP'}, {'text': 'Microsoft Teams Rooms'}], None, 'indonesia')))(__import__('app.services.hp.rulebook', fromlist=['_']), __import__('app.services.extractors.objection_playbook', fromlist=['_']))

def ex_objection_playbook__fact_guardrails():
    return (lambda g: (lambda r: ([d.as_dict()['text'] for d in r[0]], g.summarise(r[1])))(g.approve_rulebook_facts({'rule_label': 'WOLF 05', 'allowed_facts': ['HP Wolf Pro Security is the most comprehensive PC security.', 'Wolf Pro Security isolates risky attachments.'], 'conditions': [{'text': 'Supported Windows PCs'}]}, 'Jakarta, Indonesia')))(__import__('app.services.hp.guardrails', fromlist=['_']))

def ex_objection_playbook__proof_point():
    return {a: __import__('app.services.hp.case_studies', fromlist=['_']).signals_for_opportunity(a) for a in __import__('app.services.extractors.objection_playbook', fromlist=['_']).AREA_CATEGORY_COLUMNS}

def ex_objection_playbook__proof_point_score():
    return __import__('app.services.hp.case_studies', fromlist=['_'])._score({'industry': 'Education', 'signal_tags': ['Fleet-Refresh'], 'outcome': 'Cut support tickets 30%', 'source_tier': 'T0', 'challenge': 'x', 'customer': 'Univ A'}, 'Education', ['Fleet-Refresh'])[0]

def ex_objection_playbook__sector_justification_check():
    return __import__('app.services.extractors.objection_playbook', fromlist=['_'])._sector_terms_used('Across mining sites, HP Wolf Security protects devices.', 'Astra operates in automotive, mining and financial services.')

def ex_objection_playbook__hp_claim_faults():
    return __import__('app.services.extractors.objection_playbook', fromlist=['_'])._claim_faults('HP WXP integrates seamlessly with ServiceNow to cut tickets.', [{'rule_label': 'WXP 08', 'offering': 'HP Workforce Experience Platform', 'hp_line': 'HP Workforce Experience Platform', 'approved_facts': [{'text': 'WXP integrates with Microsoft Intune.', 'conditions': []}]}], 'india', 'Astra')

def ex_objection_playbook__superlative_country_case():
    return (__import__('app.services.extractors.objection_playbook', fromlist=['_'])._claim_faults('HP Wolf Security is the most trusted endpoint protection.', [], 'indonesia', 'Astra'), __import__('app.services.extractors.objection_playbook', fromlist=['_'])._claim_faults('HP Wolf Security is the most trusted endpoint protection.', [], 'Indonesia', 'Astra'))

def ex_objection_playbook__merge_near_duplicates():
    return round(__import__('difflib').SequenceMatcher(None, __import__('re').sub('[^a-z0-9 ]', '', __import__('app.services.extractors.objection_playbook', fromlist=['_'])._norm_objection('"We already standardised on Dell laptops."')), __import__('re').sub('[^a-z0-9 ]', '', __import__('app.services.extractors.objection_playbook', fromlist=['_'])._norm_objection('We already standardized on Dell laptops'))).ratio(), 3)

def ex_recent_news_signals__ls_sources():
    from app.services.extractors import recent_news_signals as r
    return r._normalize_signals([], [{'summary': 'Astra opens plant', 'effective_date': '', 'found_at': '2026-09-02', 'category': 'expands_to'}])[0]['event_date']

def ex_recent_news_signals__ls_headline_publisher():
    from app.services.extractors import recent_news_signals as r
    return r._split_headline_publisher('ASII sets IDR 36 trillion capex for 2026, up 10% year on year - IDNFinancials')

def ex_recent_news_signals__ls_duplicate_body():
    from app.services.extractors import recent_news_signals as r
    s = r._normalize_signals([{'event_headline': 'Astra opens plant - Reuters', 'news_announcements': 'Astra opens plant - Reuters', 'event_date': '2026-09-01'}], [])[0]
    return (s['evidence_sentence'], s['source_publisher'])

def ex_recent_news_signals__ls_category_map():
    from app.services.extractors import recent_news_signals as r
    return (r.NEWS_EVENTS_CATEGORY_MAP.get('expands_to', r.DEFAULT_CATEGORY), r.NEWS_EVENTS_CATEGORY_MAP.get('opens_office', r.DEFAULT_CATEGORY))

def ex_recent_news_signals__ls_gate():
    from datetime import UTC, datetime

    from app.services.extractors import recent_news_signals as r
    sigs = [{'headline': 'A', 'evidence_sentence': '', '_event_dt': datetime(2026, 9, 1, tzinfo=UTC)}, {'headline': 'B', 'evidence_sentence': '', '_event_dt': None}, {'headline': 'C', 'evidence_sentence': '', '_event_dt': datetime(2026, 10, 1, tzinfo=UTC)}, {'headline': 'D', 'evidence_sentence': '', '_event_dt': datetime(2025, 9, 1, tzinfo=UTC)}, {'headline': '', 'evidence_sentence': '', '_event_dt': datetime(2026, 9, 1, tzinfo=UTC)}]
    p, rej = r._apply_gate(sigs, datetime(2026, 9, 17, tzinfo=UTC))
    return ([s['headline'] for s in p], [x['gate_reject_reason'] for x in rej])

def ex_recent_news_signals__ls_dedup():
    from datetime import UTC, datetime

    from app.services.extractors import recent_news_signals as r
    d = r._dedupe([{'headline': 'Astra sets IDR 36 trillion capex for 2026', 'evidence_sentence': '', 'event_date': '2026-04-23', '_event_dt': datetime(2026, 4, 23, tzinfo=UTC), 'source_url': '', 'source_publisher': '', 'dataset': 'news_events', 'publication_date': ''}, {'headline': 'Astra sets IDR 36 trillion capex for 2026 year', 'evidence_sentence': '', 'event_date': '2026-04-24', '_event_dt': datetime(2026, 4, 24, tzinfo=UTC), 'source_url': 'https://www.idnfinancials.com/x', 'source_publisher': 'IDNFinancials', 'dataset': 'google_news', 'publication_date': ''}])
    return (len(d), d[0]['headline'], d[0]['source_url'], d[0]['supporting_source_count'])

def ex_recent_news_signals__ls_score():
    from app.services.extractors import signal_scoring as ss
    return ss.composite(4, 6, 8)

def ex_recent_news_signals__ls_recency():
    from datetime import UTC, datetime

    from app.services.extractors import signal_scoring as ss
    return ss.recency_points(datetime(2026, 4, 23, tzinfo=UTC), now=datetime(2026, 9, 17, tzinfo=UTC))

def ex_recent_news_signals__ls_source_reliability():
    from app.services.extractors import signal_scoring as ss
    return ss.source_reliability_points('https://news.google.com/rss/articles/CBMiopaque', 'IDNFinancials', 'google_news')[0]

def ex_recent_news_signals__ls_source_first_party():
    from app.services.extractors import signal_scoring as ss
    return ss.source_reliability_points('https://newsroom.accenture.com/news/2026/x')[:2]

def ex_recent_news_signals__ls_source_aggregator():
    from app.services.extractors import signal_scoring as ss
    return ss.source_reliability_points('https://www.prnewswire.com/news-releases/x')[0]

def ex_recent_news_signals__ls_source_structured():
    from app.services.extractors import signal_scoring as ss
    return ss.source_reliability_points('', '', 'news_events')[0]

def ex_recent_news_signals__ls_source_unknown_fallback():
    from datetime import UTC, datetime

    from app.services.extractors import recent_news_signals as r
    return r._deterministic_dims({'_event_dt': datetime(2026, 9, 1, tzinfo=UTC), 'source_url': 'https://www.localherald.co.id/x', 'source_publisher': '', 'dataset': 'google_news'}, datetime(2026, 9, 17, tzinfo=UTC))[0]

def ex_recent_news_signals__ls_source_line():
    from app.services.extractors import signal_scoring as ss
    return ss.describe_source(8, '', 'Nikkei')

def ex_recent_news_signals__ls_no_tiers_no_floor_no_cap():
    from app.services.extractors import recent_news_signals as r
    return r._tier(5.8)

def ex_recent_news_signals__ls_angle_banned():
    from app.services.extractors import recent_news_signals as r
    return r._angle_fault('Now is the time to call the CIO about the new plant.', set())

def ex_recent_news_signals__ls_angle_repetition():
    from app.services.extractors import recent_news_signals as r
    return r._angle_fault('Leadership change at Astra opens a door to the new CFO.', {'leadership change at astra opens'})

def ex_recent_news_signals__ls_angle_length():
    from app.services.extractors import recent_news_signals as r
    return r._angle_length_fault(' '.join(['word'] * 50))

def ex_recent_news_signals__ls_hp_play():
    from app.services.extractors import recent_news_signals as r
    return ('HP Wolf Security' in r.HP_PLAYS, 'HP Laptops' in r.HP_PLAYS)

def ex_solution_narrative_opportunity_map__om_intent_timing_gate():
    from app.services.extractors.solution_narrative_opportunity_map import _intent_timing_gate
    cf = {'status': 'matched', 'categories': {'3D': {'score': 34, 'stage': 'Awareness', 'has_signal': True, 'quality_flags': []}, 'PC': {'score': 12, 'stage': None, 'has_signal': False, 'quality_flags': []}, 'Poly/Collaboration': {'score': 40, 'stage': 'Consideration', 'has_signal': True, 'quality_flags': [{'term': 'teams'}]}}}
    return sorted(_intent_timing_gate(cf, True)[0])

def ex_solution_narrative_opportunity_map__om_topic_kind():
    from app.services.extractors.solution_narrative_opportunity_map import (
        _topic_governing_categories,
    )
    return (_topic_governing_categories('3D Printing'), _topic_governing_categories('Cloud Security'))

def ex_solution_narrative_opportunity_map__om_superseded_versions():
    from app.services.extractors.tech_versions import superseded
    return sorted(superseded(['Microsoft Windows 7', 'Windows 10', 'Microsoft Office 365', 'Microsoft Office 2016', 'Cisco Catalyst 6500', 'Cisco Catalyst 6503', 'SQL Server 2016', 'SQL Server 2019']))

def ex_solution_narrative_opportunity_map__om_play_eligibility():
    from app.services.extractors.solution_narrative_opportunity_map import (
        PLAY_EXCLUDE_TOKENS,
        PLAY_SIGNAL_TOKENS,
        _norm_text,
        _token_present,
    )
    t = _norm_text('CATIA V5 engineering design')
    return [pk for pk, ts in PLAY_SIGNAL_TOKENS.items() if any(_token_present(x, t) for x in ts) and (not any(_token_present(x, t) for x in PLAY_EXCLUDE_TOKENS.get(pk, [])))]

def ex_solution_narrative_opportunity_map__om_play_exclusions():
    from app.services.extractors.solution_narrative_opportunity_map import (
        PLAY_EXCLUDE_TOKENS,
        PLAY_SIGNAL_TOKENS,
        _norm_text,
        _token_present,
    )
    t = _norm_text('Vehicle device management platform')
    return [pk for pk, ts in PLAY_SIGNAL_TOKENS.items() if any(_token_present(x, t) for x in ts) and (not any(_token_present(x, t) for x in PLAY_EXCLUDE_TOKENS.get(pk, [])))]

def ex_solution_narrative_opportunity_map__om_priority():
    from app.services.extractors.solution_narrative_opportunity_map import _priority_for
    return _priority_for(True, False, True)

def ex_solution_narrative_opportunity_map__om_trigger_recency():
    from datetime import UTC, datetime, timedelta

    from app.services.extractors.solution_narrative_opportunity_map import _recency_score
    now = datetime(2026, 10, 5, tzinfo=UTC)
    return _recency_score(now - timedelta(days=45), now)

def ex_solution_narrative_opportunity_map__om_overclaim():
    from app.services.extractors.solution_narrative_opportunity_map import _has_overclaim
    return _has_overclaim('Now is the perfect time for HP. Their engineering teams require more compute. Design workloads require high-performance computing.', 'Astra International')

def ex_solution_narrative_opportunity_map__om_length_band():
    from app.services.extractors.solution_narrative_opportunity_map import _play_length_fault
    return _play_length_fault({'hp_capability': 'a ' * 20, 'inference': 'b ' * 30, 'timing_note': 'c ' * 10, 'owner_angle': None})[0]

def ex_solution_narrative_opportunity_map__om_relevance_ladder():
    from app.services.extractors.solution_narrative_opportunity_map import _play_relevance_fault
    a = _play_relevance_fault([{'dataset': 'technographics'}], ['HP Wolf Security is relevant to this opportunity.'])
    b = _play_relevance_fault([{'dataset': 'technographics'}, {'dataset': 'intent_score'}], ['HP Wolf Security is relevant to this opportunity.'])
    return ((a[1], len(a[2])), (b[1], len(b[2])))

def ex_solution_narrative_opportunity_map__om_scale_statement():
    from datetime import UTC, datetime

    from app.services.extractors.solution_narrative_opportunity_map import _build_scale_statement
    s = _build_scale_statement('pc', [{'quote': 'Laptop refresh', 'composite_score': 71.0}, {'quote': 'Astra opens 3 new plants', 'kind': 'trigger', 'dt': datetime(2026, 9, 1, tzinfo=UTC), 'dataset': 'google_news / news_events', 'field': 'event_headline'}], [], {'Number Of Employees Range': '10001+'}, ['Microsoft Windows OS', 'Windows Server 2008', 'Lenovo ThinkPad', 'Kaspersky'])
    return (s['statement'], s['fields_used'])

def ex_solution_narrative_opportunity_map__om_target_contacts():
    from app.services.extractors.solution_narrative_opportunity_map import _match_play_contacts
    roster = [{'contact_id': 1, 'full_name': 'A', 'title': 'Head of Engineering', 'normalized_department': 'Engineering & Technical', 'stakeholder_score': 80}, {'contact_id': 2, 'full_name': 'B', 'title': 'IT Manager', 'normalized_department': 'Information Technology', 'stakeholder_score': 90}, {'contact_id': 3, 'full_name': 'C', 'title': 'Design Lead', 'normalized_department': 'Marketing', 'stakeholder_score': 95}, {'contact_id': 4, 'full_name': 'D', 'title': 'CFO', 'normalized_department': 'Finance', 'stakeholder_score': 99}]
    return [c['name'] for c in _match_play_contacts('workstation', roster)]

def ex_solution_narrative_opportunity_map__om_case_study_proof():
    from app.services.hp.case_studies import lines_for_hp_line
    return lines_for_hp_line('HP Elite / Pro PCs')

def ex_solution_narrative_opportunity_map__om_cs_canonical_line():
    from app.services.hp.case_studies import canonical_line
    return [canonical_line(s) for s in [{'product_featured': 'HP Multi Jet Fusion 5200', 'hp_route': 'Print'}, {'product_featured': '', 'hp_route': 'Workstations'}, {'hp_offering': 'Poly conferencing rooms'}]]

def ex_solution_narrative_opportunity_map__om_cs_ranking():
    from app.services.hp.case_studies import _score
    sig = ['Engineering-Product-Development', 'Production-Optimization']
    a = {'industry': 'Automotive', 'signal_tags': ['Engineering-Product-Development'], 'outcome': 'cut lead time', 'source_tier': 'T0', 'challenge': 'x', 'attribution_only': False, 'merged_from_assets': 3, 'customer': 'A Co'}
    b = {'industry': 'Industrial Manufacturing', 'signal_tags': ['Production-Optimization', 'Engineering-Product-Development'], 'outcome': '', 'source_tier': 'T2', 'challenge': '', 'attribution_only': False, 'merged_from_assets': 1, 'customer': 'B Co'}
    return (_score(a, 'Automotive', sig)[0], _score(b, 'Automotive', sig)[0])

def ex_solution_narrative_opportunity_map__om_cs_industry():
    from app.services.hp.case_studies import normalise_industry
    return (normalise_industry('automation machinery manufacturing / Other Industrial Machinery Manufacturing'), normalise_industry('Motor Vehicle Manufacturing'))

def ex_solution_narrative_opportunity_map__om_cs_allocation():
    from app.services.hp.case_studies import _quality_tier
    return (_quality_tier({'industry': 'Automotive', 'attribution_only': False}, 'Automotive'), _quality_tier({'industry': 'Industrial Manufacturing', 'attribution_only': False}, 'Automotive'))

def ex_solution_narrative_opportunity_map__om_service_plays():
    from app.services.extractors.solution_narrative_opportunity_map import (
        _match_opportunity_contacts,
    )
    roster = [{'contact_id': 1, 'full_name': 'A', 'title': 'Head of Engineering', 'normalized_department': 'Engineering & Technical', 'stakeholder_score': 80}, {'contact_id': 2, 'full_name': 'B', 'title': 'IT Manager', 'normalized_department': 'Information Technology', 'stakeholder_score': 90}]
    return [c['name'] for c in _match_opportunity_contacts('Security', roster)]

def ex_solution_narrative_opportunity_map__om_sp_matching():
    from app.services.hp.rulebook import split_terms
    return split_terms({'routing_only': True, 'observable_terms': ['claims processing']}, ['financial services', 'claims processing', 'sap erp'])

def ex_solution_narrative_opportunity_map__om_sp_conditions():
    from app.services.hp.rulebook import check_conditions
    ok, unmet, unverified = check_conditions({'conditions': [{'condition_type': 'country', 'text': 'Available in the United States and in English'}, {'condition_type': 'os', 'text': 'Requires Windows 11'}, {'condition_type': 'seat_count', 'text': '500+ seats'}]}, [{'text': 'Microsoft Windows 11'}], 'Indonesia')
    return (ok, len(unmet), [c['text'] for c in unverified])

def ex_solution_narrative_opportunity_map__om_sp_iq_market():
    from app.services.hp.rulebook import iq_availability
    return [iq_availability({'matrices': {}}, c)['available'] for c in ('Indonesia', 'United States', '')]

def ex_solution_narrative_opportunity_map__om_sp_selection():
    from app.services.hp import rulebook as rb
    mk = lambda label, fam, idx, typ: {'rule': {'rule_label': label, 'part': 'B'}, 'rule_label': label, 'family': fam, 'evidence_indices': idx, 'opportunity_type': typ, 'matched_terms': [], 'modifier_only': False, 'routing_only': False, 'catalogue_only': False}
    s = rb.select([mk('CARE 03', 'CARE', [2], 'Support and Care Pack'), mk('CARE 05', 'CARE', [4], 'Support and Care Pack'), mk('WOLF 09', 'WOLF', [0, 1], 'Security')])
    return (s['primary']['rule_label'], [m['rule_label'] for m in s['secondary']], [m['rule_label'] for m in s['withheld']])

def ex_solution_narrative_opportunity_map__om_sp_confidential_facts():
    from app.services.hp.rulebook import _confidential_fact_allowed
    return [_confidential_fact_allowed('Saves up to 50% on ink', []), _confidential_fact_allowed('Saves up to 50% on ink', ['with Instant Ink plan']), _confidential_fact_allowed('Original HP Ink is reliable', [])]

def ex_solution_narrative_opportunity_map__om_evidence_tier():
    from app.services.hp.evidence_tier import tier_for
    return tier_for([{'dataset': 'technographics'}, {'dataset': 'google_news'}, {'dataset': 'news_events'}])['tier']

def ex_stakeholder_map__withhold_pending_review():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_'])._drop_unmatched_contacts([{'match_status': 'Pending review'}, {'apollo_match_status': 'Matched'}, {'Match Status': ''}, {'match_status': 'Needs Review'}])

def ex_stakeholder_map__contact_field_precedence():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).resolve_field({'Prospect job_title': 'nan', 'apollo_title': 'CTO'}, ['Prospect job_title', 'apollo_title'])

def ex_stakeholder_map__phone_normalisation():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).normalize_phone('6281293986658.0')

def ex_stakeholder_map__department_normalisation():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).normalize_department('c_suite; master_operations')

def ex_stakeholder_map__seniority_banding():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).seniority_band('head', 'Head of IT Infrastructure')

def ex_stakeholder_map__c_suite_corroboration():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).seniority_band('c_suite', 'CIO Office')

def ex_stakeholder_map__stakeholder_score():
    return (lambda sm: (lambda b, inf: (lambda c: dict(band=b, influence=inf, components=c, composite=sm.composite_score(c), relevance_band=sm.hp_relevance_band(c['hp_relevance']), priority_contact=sm.composite_score(c) >= sm.PRIORITY_CONTACT_MIN_COMPOSITE and sm.hp_relevance_band(c['hp_relevance']) != 'low'))({'seniority': sm.score_seniority(b), 'hp_relevance': sm.score_hp_relevance('Head of IT Procurement', sm.normalize_department('it'), 'SAP'), 'influence': sm.score_influence(inf), 'data_completeness': sm.score_data_completeness('a@x.com', 'valid', '+6281200000000', 'linkedin.com/in/x', 'SAP'), 'priority': sm.score_priority(sm.assign_priority(sm.normalize_department('it'), b))}))(sm.seniority_band('head', 'Head of IT Procurement')[0], sm.assign_influence('IT Decision Maker', 'Head of IT Procurement', sm.seniority_band('head', 'Head of IT Procurement')[0], sm.normalize_department('it'))[0]))(__import__('app.services.extractors.stakeholder_map', fromlist=['_']))

def ex_stakeholder_map__score_seniority():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).score_seniority('VP')

def ex_stakeholder_map__score_hp_relevance():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).score_hp_relevance('Cloud Architect', 'Engineering & Technical', 'Azure, AWS')

def ex_stakeholder_map__hp_relevance_department_text():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).score_hp_relevance('Sales Manager', 'Information Technology', None)

def ex_stakeholder_map__non_it_title_cap():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).score_hp_relevance('Employment Relations Lead', 'Information Technology', None)

def ex_stakeholder_map__hp_relevance_band():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).hp_relevance_band(69)

def ex_stakeholder_map__influence_type():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).assign_influence('IT Decision Maker', 'Tax Division Head', 'Director', 'Information Technology')

def ex_stakeholder_map__influence_substring_effects():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).assign_influence(None, 'Internal Audit Manager', 'Manager', 'Finance')

def ex_stakeholder_map__score_influence():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).score_influence('Technical Evaluator')

def ex_stakeholder_map__score_data_completeness():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).score_data_completeness('a@x.com', 'catch-all', None, 'linkedin.com/in/a', None)

def ex_stakeholder_map__priority_level():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).assign_priority('Finance', 'C-Suite')

def ex_stakeholder_map__priority_contacts():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).composite_score({'seniority': 25, 'hp_relevance': 40, 'influence': 50, 'data_completeness': 55, 'priority': 10}) >= __import__('app.services.extractors.stakeholder_map', fromlist=['_']).PRIORITY_CONTACT_MIN_COMPOSITE

def ex_stakeholder_map__roster_order():
    return sorted(['VP', 'Manager', 'C-Suite', 'Unknown', 'Director'], key=__import__('app.services.extractors.stakeholder_map', fromlist=['_']).seniority_rank)

def ex_stakeholder_map__client_buying_committee_coverage():
    return {k: v for k, v in __import__('app.services.extractors.personas', fromlist=['_']).coverage([{'target_persona': 'Head of Procurement', 'department': 'Procurement', 'buying_committee_angle': 'Economic Buyer', 'contact_name': '', 'actual_job_title': '', 'work_email': '', 'phone_number': '', 'source': '', 'contact_status': 'No suitable distinct candidate found', 'is_filled': False}, {'target_persona': 'IT Asset Manager', 'department': 'IT', 'buying_committee_angle': 'Technical Buyer', 'contact_name': 'A B', 'actual_job_title': 'IT Asset Lead', 'work_email': 'a@b.com', 'phone_number': '', 'source': 'Apollo', 'contact_status': '', 'is_filled': True}, {'target_persona': 'CFO', 'department': 'Finance', 'buying_committee_angle': 'Finance - Budget Owner', 'contact_name': 'C D', 'actual_job_title': 'CFO', 'work_email': '', 'phone_number': '', 'source': 'Apollo', 'contact_status': '', 'is_filled': True}]).items() if k in ('target_roles', 'filled_roles', 'roles_with_a_contact_detail', 'coverage_percent')}

def ex_stakeholder_map__do_not_propose_list():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_']).blocked_plays_for('Head of Cloud Operations')

def ex_stakeholder_map__tp_grounding_check():
    return __import__('app.services.extractors.grounding', fromlist=['_']).corpus_from_texts(['ASII sets IDR 36 trillion capex for 2026']).unsourced_numbers('Astra plans 40 trillion of capex in 2026, up 36 trillion')

def ex_stakeholder_map__tp_decision_power_echo():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_'])._is_rule_echo('This role typically participates in or owns decisions of this kind.')

def ex_stakeholder_map__tp_no_hardware_override():
    return (lambda sm, gr: not sm.remit_reaches_hardware('Head of Tax Division') and next((c for t, c in gr.HP_LINE_TOKENS if any(x in 'i would like to discuss how hp elitebook devices could support your tax teams. pc - fleet standardisation' for x in t)), None))(__import__('app.services.extractors.stakeholder_map', fromlist=['_']), __import__('app.services.extractors.grounding', fromlist=['_']))

def ex_stakeholder_map__tp_pain_point_filter():
    return __import__('app.services.extractors.stakeholder_map', fromlist=['_'])._is_evidence_label('Cloud computing', {'cloud computing'})

def ex_stakeholder_map__persona_role_match():
    return __import__('app.services.hp.buyer_personas', fromlist=['_']).match_role('Chief Financial Officer (CFO)')

def ex_stakeholder_map__persona_ask_bounds():
    return __import__('app.services.hp.buyer_personas', fromlist=['_']).ask_bound('head-procurement')

def ex_stakeholder_map__persona_line_eligibility():
    return __import__('app.services.hp.buyer_personas', fromlist=['_']).is_line_allowed('cfo', 'Poly Studio')

def ex_strategy_chat__sc_snapshot_widget():
    return [(p['id'], p['prompt_text']) for p in __import__('app.services.extractors.strategy_chat', fromlist=['_'])._suggested_prompts('Astra')]

def ex_strategy_chat__sc_context_payload():
    return (__import__('app.services.strategy.context', fromlist=['_'])._sort_key('exec_summary_card'), __import__('app.services.strategy.context', fromlist=['_'])._sort_key('zzz_new_widget'))

def ex_strategy_chat__sc_small_talk():
    return [__import__('app.services.strategy.chat', fromlist=['_'])._is_small_talk(q) for q in ('hi', 'Who is the CEO?', 'ok')]

def ex_strategy_chat__sc_fact_check():
    return (lambda c, k, P: k.validate(k.parse({'segments': [{'id': 'c1', 'type': 'FACT', 'block': 'paragraph', 'text': 'They run SolidWorks.', 'sections': ['tech_stack_matrix'], 'quote': 'SolidWorks'}, {'id': 'c2', 'type': 'SYNTHESIS', 'block': 'paragraph', 'text': 'So Siemens NX is next.', 'depends_on': ['c1']}, {'id': 'c3', 'type': 'GENERAL', 'block': 'paragraph', 'text': 'Most estates of 4,000 seats refresh every 4 years.'}]}), widget_keys=['tech_stack_matrix', 'opportunity_narrative_plays'], section_texts=c._section_texts(P), corpus=c._corpus_for(P), company='Astra', payload=P, question='Which line has the strongest case?'))(__import__('app.services.strategy.chat', fromlist=['_']), __import__('app.services.strategy.claims', fromlist=['_']), '===== tech_stack_matrix (feature: tech_landscape) =====\n{"families":["AutoCAD","CATIA"],"total":281}\n\n===== opportunity_narrative_plays (feature: opportunity_map) =====\n{"plays":[{"title":"Workstations","priority":"Critical"}]}')

def ex_strategy_chat__sc_synthesis_check():
    return (lambda c, k, P: k.validate(k.parse({'segments': [{'id': 'c1', 'type': 'GENERAL', 'block': 'heading', 'text': 'ANSWER:'}, {'id': 'c2', 'type': 'FACT', 'block': 'paragraph', 'text': 'Their estate runs AutoCAD and CATIA.', 'sections': ['tech_stack_matrix'], 'quote': 'AutoCAD'}, {'id': 'c3', 'type': 'FACT', 'block': 'paragraph', 'text': 'Workstations are rated Critical.', 'sections': ['opportunity_narrative_plays'], 'quote': 'Critical'}, {'id': 'c4', 'type': 'SYNTHESIS', 'block': 'paragraph', 'text': 'So the workstation line has the strongest case.', 'depends_on': ['c2', 'c3']}, {'id': 'c5', 'type': 'RECOMMENDATION', 'block': 'bullet', 'text': 'Open on the CAD estate in week 1, then send three touches over 30 days.', 'depends_on': ['c2']}]}), widget_keys=['tech_stack_matrix', 'opportunity_narrative_plays'], section_texts=c._section_texts(P), corpus=c._corpus_for(P), company='Astra', payload=P, question='Which line has the strongest case?'))(__import__('app.services.strategy.chat', fromlist=['_']), __import__('app.services.strategy.claims', fromlist=['_']), '===== tech_stack_matrix (feature: tech_landscape) =====\n{"families":["AutoCAD","CATIA"],"total":281}\n\n===== opportunity_narrative_plays (feature: opportunity_map) =====\n{"plays":[{"title":"Workstations","priority":"Critical"}]}')

def ex_strategy_chat__sc_plan_figures():
    return sorted(__import__('app.services.strategy.claims', fromlist=['_'])._plan_figures('three touches over 30 days, week 2 and a 90-day plan, 30/60/90'))

def ex_strategy_chat__sc_whole_answer_checks():
    return __import__('app.services.strategy.claims', fromlist=['_'])._unsupported_hp_line('Lead with HP Wolf Security.', '===== tech_stack_matrix (feature: tech_landscape) =====\n{"families":["AutoCAD","CATIA"],"total":281}\n\n===== opportunity_narrative_plays (feature: opportunity_map) =====\n{"plays":[{"title":"Workstations","priority":"Critical"}]}')

def ex_strategy_chat__sc_retry_partial():
    return (lambda c, k, P: (lambda S: k.surviving(S, k.validate(S, widget_keys=['tech_stack_matrix', 'opportunity_narrative_plays'], section_texts=c._section_texts(P), corpus=c._corpus_for(P), company='Astra', payload=P, question='q')[1]))(k.parse({'segments': [{'id': 'c1', 'type': 'FACT', 'block': 'paragraph', 'text': 'They run SolidWorks.', 'sections': ['tech_stack_matrix'], 'quote': 'SolidWorks'}, {'id': 'c2', 'type': 'SYNTHESIS', 'block': 'paragraph', 'text': 'So Siemens NX is next.', 'depends_on': ['c1']}, {'id': 'c3', 'type': 'GENERAL', 'block': 'paragraph', 'text': 'Most estates of 4,000 seats refresh every 4 years.'}]})))(__import__('app.services.strategy.chat', fromlist=['_']), __import__('app.services.strategy.claims', fromlist=['_']), '===== tech_stack_matrix (feature: tech_landscape) =====\n{"families":["AutoCAD","CATIA"],"total":281}\n\n===== opportunity_narrative_plays (feature: opportunity_map) =====\n{"plays":[{"title":"Workstations","priority":"Critical"}]}')

def ex_strategy_chat__sc_render():
    return (lambda c, k: k.render(k.parse({'segments': [{'id': 'c1', 'type': 'GENERAL', 'block': 'heading', 'text': 'ANSWER:'}, {'id': 'c2', 'type': 'FACT', 'block': 'paragraph', 'text': 'Their estate runs AutoCAD and CATIA.', 'sections': ['tech_stack_matrix'], 'quote': 'AutoCAD'}, {'id': 'c3', 'type': 'FACT', 'block': 'paragraph', 'text': 'Workstations are rated Critical.', 'sections': ['opportunity_narrative_plays'], 'quote': 'Critical'}, {'id': 'c4', 'type': 'SYNTHESIS', 'block': 'paragraph', 'text': 'So the workstation line has the strongest case.', 'depends_on': ['c2', 'c3']}, {'id': 'c5', 'type': 'RECOMMENDATION', 'block': 'bullet', 'text': 'Open on the CAD estate in week 1, then send three touches over 30 days.', 'depends_on': ['c2']}]})))(__import__('app.services.strategy.chat', fromlist=['_']), __import__('app.services.strategy.claims', fromlist=['_']))

def ex_strategy_chat__sc_roleplay_personas():
    return __import__('app.services.strategy.personas', fromlist=['_']).prompt_block({'title': 'Chief Operating Officer', 'department': 'Executive', 'seniority_band': 'C-Suite', 'influence_type': 'Decision Maker', 'pain_points': ['a', 'b', 'c', 'd', 'e'], 'objections': [{'objection': 'We already standardise on Dell', 'area': 'Client Devices'}]})

def ex_strategy_chat__sc_roleplay_validator():
    return [__import__('app.services.strategy.chat', fromlist=['_'])._validate_roleplay(t, '===== tech_stack_matrix (feature: tech_landscape) =====\n{"families":["AutoCAD","CATIA"],"total":281}\n\n===== opportunity_narrative_plays (feature: opportunity_map) =====\n{"plays":[{"title":"Workstations","priority":"Critical"}]}', ['tech_stack_matrix', 'opportunity_narrative_plays'], ['Budi Santoso', 'Santoso'])[:2] for t in ('Hmm. Go on. We run AutoCAD and CATIA [tech_stack_matrix]. What would switching gain us?', 'Talk to Santoso about it.', 'We are locked into a three-year agreement.')]

def ex_strategy_chat__sc_roleplay_starters():
    return [p['id'] for p in __import__('app.services.strategy.personas', fromlist=['_']).suggested_prompts({'title': 'COO', 'pain_points': ['x'], 'objections': [{'area': 'Client Devices'}, {'area': 'Print / MPS'}, {'area': 'Collaboration'}]})]

def ex_strategy_chat__sc_prose_validator():
    return [__import__('app.services.strategy.chat', fromlist=['_'])._validate(t, '===== tech_stack_matrix (feature: tech_landscape) =====\n{"families":["AutoCAD","CATIA"],"total":281}\n\n===== opportunity_narrative_plays (feature: opportunity_map) =====\n{"plays":[{"title":"Workstations","priority":"Critical"}]}', ['tech_stack_matrix', 'opportunity_narrative_plays'])[:2] for t in ('They run AutoCAD [tech_stack_matrix]. They have 500 engineers [tech_stack_matrix].', 'They run AutoCAD [exec_key_metrics].', 'They run AutoCAD. Workstations are a Critical play [opportunity_narrative_plays].')]

def ex_tech_landscape__tl_technology_sources():
    from app.services.extractors.tech_landscape import detected_technologies
    return detected_technologies([{'Full Tech Stack': 'Microsoft Windows 10, Microsoft Intune, Kaspersky'}], [{'Technologies Used By Company Website': 'Akamai, Google Analytics'}], [], {'categories': {'PC': {'related_technologies': ['Microsoft Intune', 'ServiceNow']}}})

def ex_tech_landscape__tl_website_fallback():
    from app.services.extractors.tech_landscape import detected_technologies
    return detected_technologies([], [{'Technologies Used By Company Website': 'Akamai, Google Analytics'}], [{'Hosting': 'Other: Akamai Hosted, AWS', 'Seo Title': 'Home'}], {})[2]

def ex_tech_landscape__tl_category_cards():
    from app.services.extractors.tech_landscape import _kw_in
    return _kw_in('g suite', 'adobe digital marketing suite')

def ex_tech_landscape__tl_client_os_keywords():
    from app.services.extractors.tech_landscape import CLIENT_OS_APPLE, _kw_in
    return [k for k in CLIENT_OS_APPLE if _kw_in(k, 'mac os x 10.15')]

def ex_tech_landscape__tl_relationship_and_risk():
    from app.services.extractors.tech_landscape import _normalise_hp_fields
    c = [{'category_key': 'pc_laptop_brands', 'status_badge': 'Displacement opportunity', 'vendors': [{'vendor_name': 'HP Inc.', 'is_whitespace': True}]}]
    _normalise_hp_fields(c, {})
    return (c[0]['status_badge'], c[0]['hp_relationship_label'], c[0]['vendors'][0]['risk_level'])

def ex_tech_landscape__tl_detection_status():
    from app.services.extractors.tech_landscape import _normalise_hp_fields
    c = [{'category_key': 'it_security_parity', 'status_badge': 'Complementary attach', 'vendors': [{'vendor_name': 'Symantec / Kaspersky', 'detected_as': ['Kaspersky']}]}]
    _normalise_hp_fields(c, {'It Security': 'Kaspersky, Okta', 'Full Tech Stack': 'Kaspersky'})
    return (c[0]['vendors'][0]['detection_status'], c[0]['vendors'][0]['provenance'])

def ex_tech_landscape__tl_map_narrative():
    from app.services.extractors.grounding import corpus_from_texts
    from app.services.hp.map_narrative import _is_acceptable
    c = corpus_from_texts(['Microsoft Windows 10', 'Astra'])
    return [_is_acceptable(t, c) for t in ['HP Wolf Security guarantees protection', 'Wolf Security reduces incidents by 30%', 'Wolf Security adds below-the-OS protection alongside Kaspersky']]

def ex_tech_landscape__tl_rulebook_offering_override():
    from app.services.extractors.tech_landscape import _rulebook_offering
    book = {'routing': [], 'matrices': {}, 'rules': [{'rule_label': 'WOLF 09', 'family': 'WOLF', 'part': 'B', 'order': 9, 'offering': 'HP Wolf Pro Security', 'signal_tokens': ['kaspersky'], 'allowed_facts': ['Wolf Pro Security adds isolation.'], 'conditions': []}]}
    o = _rulebook_offering(book, {'vendor_name': 'Symantec / Kaspersky', 'detected_as': ['Kaspersky Endpoint Security']}, 'Poly Collaboration')
    return (o['rule_label'], o['hp_line'], o['line_changed'])

def ex_tech_landscape__tl_confidence_score():
    from app.services.hp.tech_confidence import confidence
    return confidence(10, 5)

def ex_tech_landscape__tl_driver_1():
    from app.services.hp.tech_confidence import driver_1_technology
    return driver_1_technology(['Microsoft Windows'], None)[0:2]

def ex_tech_landscape__tl_driver_1_route():
    from app.services.hp.tech_confidence import driver_1_technology
    return driver_1_technology(['VMware'], None)[0]

def ex_tech_landscape__tl_driver_1_related_family():
    from app.services.hp.tech_confidence import ROUTE_WXP, driver_1_technology
    return driver_1_technology(['Microsoft Azure'], ROUTE_WXP)[0]

def ex_tech_landscape__tl_driver_1_card_fallback():
    from app.services.hp.tech_confidence import ROUTE_WOLF, driver_1_for_card
    return driver_1_for_card(['Kaspersky Endpoint Security'], ROUTE_WOLF, 'HP Wolf Security')[0]

def ex_tech_landscape__tl_driver_2():
    from app.services.hp.tech_confidence import driver_2_intent
    return driver_2_intent(34, '3D')

def ex_tech_landscape__tl_suppression_guardrail():
    from app.services.hp.tech_confidence import confidence, is_publishable
    return (confidence(0, 10), is_publishable(0))

def ex_tech_landscape__tl_reconcile_after_suppression():
    from app.services.extractors.tech_landscape import _reconcile_after_suppression
    c = [{'category_key': 'client_os', 'detected_signals_count': 2, 'what_it_means': 'Microsoft Windows and Apple macOS dominate the estate.', 'vendors': [{'vendor_name': 'Microsoft'}]}]
    r = _reconcile_after_suppression(c, [{'category': 'client_os', 'vendor': 'Apple'}])
    return (c[0]['detected_signals_count'], c[0]['what_it_means'])

def ex_tech_landscape__tl_case_study_proof():
    from app.services.hp import case_studies as cs
    return (cs.lines_for_product_text('HP Wolf Security'), cs.signals_for_opportunity('IT Security & Endpoint Protection'))

def ex_tech_landscape__tl_integration_routes():
    from app.services.hp.integration_routes import routes_for
    return [l['text'] for l in routes_for(['Microsoft Intune', 'ServiceNow', 'Cisco Routers'], [{'allowed_facts': ['HP WXP integrates with ServiceNow, Microsoft Intune, Power BI and Tableau.'], 'offering': 'HP Workforce Experience Platform', 'rule_label': 'WXP 07', 'family': 'WXP'}])]

def ex_tech_landscape__tl_stack_matrix_groups():
    from app.services.extractors.tech_landscape import _category_names
    return _category_names('Python, Java, Google Cloud APIs (+16 more)')

def ex_tech_landscape__tl_stack_view():
    from app.services.extractors.tech_landscape import stack_view
    sv = stack_view({'It Security': ['Kaspersky'], 'Sales': ['Kaspersky'], 'Bi And Analytics': ['Tableau']}, ['Kaspersky', 'Tableau', 'Jira'], {}, [{'category_name': 'IT Security & Endpoint Protection', 'vendors': [{'vendor_name': 'Symantec / Kaspersky', 'detected_as': ['Kaspersky'], 'hp_play': {'product': 'HP Wolf Security', 'play_text': 'x'}, 'risk_level': 'Low risk'}]}])
    return ([t['family'] for t in sv['technologies']], sv['hp_relevant_count'], sv['total'])

def ex_tech_landscape__tl_webstack_breakdown():
    from app.services.extractors.tech_landscape import _parse_tech_breakdown
    return _parse_tech_breakdown([{'Company Name': 'Astra', 'Cms': 'Enterprise: Adobe Experience Manager | Other: WordPress 5.3, Investis'}])[0]['groups']

def ex_tech_landscape__tl_rec_evidence_corpus():
    from app.services.hp.rulebook import _is_meaningful
    return (_is_meaningful('title', 'Data Engineer - AI platform'), _is_meaningful('posted_date', '2026-09-01'))

def ex_tech_landscape__tl_rec_rule_matching():
    from app.services.hp import rulebook as rb
    book = {'routing': [], 'matrices': {}, 'rules': [{'rule_label': 'WOLF 09', 'family': 'WOLF', 'part': 'B', 'order': 9, 'offering': 'HP Wolf Pro Security', 'signal_tokens': ['kaspersky', 'symantec endpoint protection'], 'allowed_facts': ['a'], 'conditions': []}, {'rule_label': 'WOLF 10', 'family': 'WOLF', 'part': 'B', 'order': 10, 'offering': 'HP Sure Click Enterprise', 'signal_tokens': ['kaspersky'], 'allowed_facts': ['b'], 'conditions': []}, {'rule_label': 'CARE 03', 'family': 'CARE', 'part': 'B', 'order': 3, 'offering': 'HP Care Pack', 'signal_tokens': ['help desk', 'ticket volume'], 'allowed_facts': ['c'], 'conditions': [{'condition_type': 'seat_count', 'text': 'At least 500 seats'}]}, {'rule_label': 'PRINT 21', 'family': 'PRINT', 'part': 'B', 'order': 21, 'offering': 'TROY', 'signal_tokens': ['sap erp'], 'allowed_facts': ['d'], 'conditions': []}, {'rule_label': 'IQ 02', 'family': 'IQ', 'part': 'B', 'order': 2, 'offering': 'HP IQ', 'signal_tokens': ['kaspersky'], 'allowed_facts': ['e'], 'conditions': []}]}
    ev = [{'text': 'Kaspersky Endpoint Security'}, {'text': 'Symantec Endpoint Protection'}, {'text': 'IT Help Desk Analyst - high ticket volume'}, {'text': 'SAP ERP'}]
    drops = []
    return ([m['rule_label'] for m in rb.candidates(book, ev, None, 'Indonesia', drops=drops)], [d['rule_label'] for d in drops])

def ex_tech_landscape__tl_rec_selection():
    from app.services.hp import rulebook as rb
    mk = lambda label, fam, idx, typ: {'rule': {'rule_label': label, 'part': 'B'}, 'rule_label': label, 'family': fam, 'evidence_indices': idx, 'opportunity_type': typ, 'matched_terms': [], 'modifier_only': False, 'routing_only': False, 'catalogue_only': False}
    s = rb.select([mk('WOLF 09', 'WOLF', [0, 1], 'Security'), mk('CARE 03', 'CARE', [2], 'Support and Care Pack'), mk('WOLF 10', 'WOLF', [0], 'Security')])
    return (s['primary']['rule_label'], [m['rule_label'] for m in s['secondary']], [(m['rule_label'], m['withheld_because']) for m in s['withheld']])

def ex_tech_landscape__tl_rec_part_a_placement():
    from app.services.hp.product_rules import RULES_BY_ID
    from app.services.hp.recommendations import DEVICE_TYPE_TO_CATEGORY
    return DEVICE_TYPE_TO_CATEGORY[RULES_BY_ID[10]['device_type']]

def ex_tech_landscape__tl_rec_part_b_cards():
    from app.services.hp.recommendations import _category_families
    return _category_families({'vendors': [{'hp_play': {'product': 'HP Wolf Security'}}]})

def ex_tech_landscape__tl_rec_lifecycle():
    from datetime import date

    from app.services.hp.lifecycle import status_for
    rows = [{'product': 'HP EliteBook 8 G1i', 'generations': ['g1i'], 'identity': ['elitebook', '8'], 'first_end': '2026-03-01', 'last_end': '2027-01-31'}, {'product': 'HP ProBook 4 G1i', 'generations': ['g1i'], 'identity': ['probook', '4'], 'first_end': '2025-01-01', 'last_end': '2026-06-30'}]
    return [status_for(o, date(2026, 10, 5), rows)['status'] for o in ['HP EliteBook 8 G1i Series', 'HP ProBook 4 G1i', 'HP EliteBook 8 G2 Series']]

def ex_tech_landscape__tl_rec_fact_guardrails():
    from app.services.hp.guardrails import approve_rulebook_facts
    ap, rj = approve_rulebook_facts({'rule_label': '8', 'allowed_facts': ['up to 85% higher CPU performance', 'up to 61% better office productivity on the cited Procyon test', 'Sure View privacy screen', 'optional Sure View on select models'], 'requires_exact_competitor': True, 'conditions': []}, 'United States')
    return ([d.as_dict()['text'] for d in ap], [d.as_dict()['guardrail'] for d in rj])

def ex_tech_landscape__tl_rec_confidence_band():
    from app.services.hp.recommendations import _category_status_for_rule, _confidence_for
    cats = [{'category_name': n, 'status_badge': s} for n, s in [('Client OS', 'Contextual - no direct HP line'), ('PC/Laptop Brands', 'Displacement opportunity'), ('Workstations & High-Performance Compute', 'Displacement opportunity')]]
    return [_confidence_for(_category_status_for_rule(cats, {'device_type': d}), True, {})[0] for d in ('notebook', 'tower')]

def ex_tech_landscape__tl_rec_evidence_tier():
    from app.services.hp.evidence_tier import tier_for
    return tier_for([{'dataset': 'technographics'}, {'dataset': 'intent_score'}], category_intent=0)['tier']

def ex_tech_landscape__tl_rec_llm_prose():
    from app.services.hp.guardrails import tier_language_faults
    return len(tier_language_faults('Astra needs to replace its endpoint antivirus. HP Wolf Security requires a supported Windows PC.', 'Conversation Starter'))


EXAMPLES = {
    ('content_studio', 'cs_account_evidence_lines'): ex_content_studio__cs_account_evidence_lines,
    ('content_studio', 'cs_hiring_clusters'): ex_content_studio__cs_hiring_clusters,
    ('content_studio', 'cs_grounding_corpus'): ex_content_studio__cs_grounding_corpus,
    ('content_studio', 'cs_persona_selection'): ex_content_studio__cs_persona_selection,
    ('content_studio', 'cs_persona_evidence'): ex_content_studio__cs_persona_evidence,
    ('content_studio', 'cs_named_vs_role'): ex_content_studio__cs_named_vs_role,
    ('content_studio', 'cs_one_pager_contract'): ex_content_studio__cs_one_pager_contract,
    ('content_studio', 'cs_line_eligibility'): ex_content_studio__cs_line_eligibility,
    ('content_studio', 'cs_line_qualifiers'): ex_content_studio__cs_line_qualifiers,
    ('content_studio', 'cs_one_line_max'): ex_content_studio__cs_one_line_max,
    ('content_studio', 'cs_ask_bound'): ex_content_studio__cs_ask_bound,
    ('content_studio', 'cs_validator'): ex_content_studio__cs_validator,
    ('content_studio', 'cs_g1'): ex_content_studio__cs_g1,
    ('content_studio', 'cs_g2'): ex_content_studio__cs_g2,
    ('content_studio', 'cs_g3'): ex_content_studio__cs_g3,
    ('content_studio', 'cs_g7'): ex_content_studio__cs_g7,
    ('content_studio', 'cs_g8'): ex_content_studio__cs_g8,
    ('content_studio', 'cs_g9'): ex_content_studio__cs_g9,
    ('content_studio', 'cs_g10'): ex_content_studio__cs_g10,
    ('content_studio', 'cs_g11'): ex_content_studio__cs_g11,
    ('content_studio', 'cs_g12'): ex_content_studio__cs_g12,
    ('content_studio', 'cs_g13'): ex_content_studio__cs_g13,
    ('content_studio', 'cs_fallback'): ex_content_studio__cs_fallback,
    ('content_studio', 'cs_greeting'): ex_content_studio__cs_greeting,
    ('content_studio', 'cs_proof_point'): ex_content_studio__cs_proof_point,
    ('content_studio', 'cs_audit_ledger'): ex_content_studio__cs_audit_ledger,
    ('content_studio', 'cs_claim_quality'): ex_content_studio__cs_claim_quality,
    ('content_studio', 'cs_country_guardrails'): ex_content_studio__cs_country_guardrails,
    ('content_studio', 'cs_tier_language'): ex_content_studio__cs_tier_language,
    ('executive_dashboard', 'summary_parent_company'): ex_executive_dashboard__summary_parent_company,
    ('executive_dashboard', 'summary_subsidiaries'): ex_executive_dashboard__summary_subsidiaries,
    ('executive_dashboard', 'summary_description_bullets'): ex_executive_dashboard__summary_description_bullets,
    ('executive_dashboard', 'filings_on_record'): ex_executive_dashboard__filings_on_record,
    ('executive_dashboard', 'reported_financials'): ex_executive_dashboard__reported_financials,
    ('executive_dashboard', 'financials_usable'): ex_executive_dashboard__financials_usable,
    ('executive_dashboard', 'financials_growth'): ex_executive_dashboard__financials_growth,
    ('executive_dashboard', 'financials_series_display'): ex_executive_dashboard__financials_series_display,
    ('executive_dashboard', 'ceo'): ex_executive_dashboard__ceo,
    ('executive_dashboard', 'exec_hiring_velocity'): ex_executive_dashboard__exec_hiring_velocity,
    ('executive_dashboard', 'hiring_country_check'): ex_executive_dashboard__hiring_country_check,
    ('executive_dashboard', 'hiring_window'): ex_executive_dashboard__hiring_window,
    ('executive_dashboard', 'urgency_score'): ex_executive_dashboard__urgency_score,
    ('executive_dashboard', 'urgency_coverage_gate'): ex_executive_dashboard__urgency_coverage_gate,
    ('executive_dashboard', 'urgency_explanation'): ex_executive_dashboard__urgency_explanation,
    ('executive_dashboard', 'driver_workplace_os'): ex_executive_dashboard__driver_workplace_os,
    ('executive_dashboard', 'wos_account_scale'): ex_executive_dashboard__wos_account_scale,
    ('executive_dashboard', 'wos_os_environment'): ex_executive_dashboard__wos_os_environment,
    ('executive_dashboard', 'wos_footprint'): ex_executive_dashboard__wos_footprint,
    ('executive_dashboard', 'driver_ai_workstation'): ex_executive_dashboard__driver_ai_workstation,
    ('executive_dashboard', 'ai_breadth'): ex_executive_dashboard__ai_breadth,
    ('executive_dashboard', 'ai_depth'): ex_executive_dashboard__ai_depth,
    ('executive_dashboard', 'ai_workstation_intent'): ex_executive_dashboard__ai_workstation_intent,
    ('executive_dashboard', 'ai_recent_events'): ex_executive_dashboard__ai_recent_events,
    ('executive_dashboard', 'driver_growth_expansion'): ex_executive_dashboard__driver_growth_expansion,
    ('executive_dashboard', 'growth_workforce'): ex_executive_dashboard__growth_workforce,
    ('executive_dashboard', 'growth_hiring_volume'): ex_executive_dashboard__growth_hiring_volume,
    ('executive_dashboard', 'growth_events'): ex_executive_dashboard__growth_events,
    ('executive_dashboard', 'driver_hp_solution_intent'): ex_executive_dashboard__driver_hp_solution_intent,
    ('executive_dashboard', 'hpi_strength'): ex_executive_dashboard__hpi_strength,
    ('executive_dashboard', 'hpi_trend'): ex_executive_dashboard__hpi_trend,
    ('executive_dashboard', 'hpi_stage'): ex_executive_dashboard__hpi_stage,
    ('executive_dashboard', 'hpi_volume'): ex_executive_dashboard__hpi_volume,
    ('executive_dashboard', 'priority_relevance_gate'): ex_executive_dashboard__priority_relevance_gate,
    ('executive_dashboard', 'priority_dedup'): ex_executive_dashboard__priority_dedup,
    ('executive_dashboard', 'evidence_strength'): ex_executive_dashboard__evidence_strength,
    ('executive_dashboard', 'es_filing'): ex_executive_dashboard__es_filing,
    ('executive_dashboard', 'es_recency'): ex_executive_dashboard__es_recency,
    ('executive_dashboard', 'es_diversity'): ex_executive_dashboard__es_diversity,
    ('executive_dashboard', 'catalyst_description'): ex_executive_dashboard__catalyst_description,
    ('executive_dashboard', 'claim_points'): ex_executive_dashboard__claim_points,
    ('executive_dashboard', 'executive_summary_text'): ex_executive_dashboard__executive_summary_text,
    ('intent_demand_signals', 'int_lead_source'): ex_intent_demand_signals__int_lead_source,
    ('intent_demand_signals', 'int_domain_match'): ex_intent_demand_signals__int_domain_match,
    ('intent_demand_signals', 'int_topics_table'): ex_intent_demand_signals__int_topics_table,
    ('intent_demand_signals', 'int_topic_dedup_exclusion'): ex_intent_demand_signals__int_topic_dedup_exclusion,
    ('intent_demand_signals', 'int_intensity'): ex_intent_demand_signals__int_intensity,
    ('intent_demand_signals', 'int_dictionary_mapping'): ex_intent_demand_signals__int_dictionary_mapping,
    ('intent_demand_signals', 'int_mapping_conflicts'): ex_intent_demand_signals__int_mapping_conflicts,
    ('intent_demand_signals', 'int_hiring_linked_tag'): ex_intent_demand_signals__int_hiring_linked_tag,
    ('intent_demand_signals', 'int_theme_stats'): ex_intent_demand_signals__int_theme_stats,
    ('intent_demand_signals', 'int_category_file'): ex_intent_demand_signals__int_category_file,
    ('intent_demand_signals', 'int_has_signal'): ex_intent_demand_signals__int_has_signal,
    ('intent_demand_signals', 'int_trend_and_flags'): ex_intent_demand_signals__int_trend_and_flags,
    ('intent_demand_signals', 'int_top_check'): ex_intent_demand_signals__int_top_check,
    ('intent_demand_signals', 'int_supporting_signals'): ex_intent_demand_signals__int_supporting_signals,
    ('intent_demand_signals', 'int_tech_inventory'): ex_intent_demand_signals__int_tech_inventory,
    ('intent_demand_signals', 'int_category_explanation'): ex_intent_demand_signals__int_category_explanation,
    ('intent_demand_signals', 'int_evidence_tier'): ex_intent_demand_signals__int_evidence_tier,
    ('intent_demand_signals', 'int_so_what_category'): ex_intent_demand_signals__int_so_what_category,
    ('intent_demand_signals', 'int_tier_wording_guard'): ex_intent_demand_signals__int_tier_wording_guard,
    ('intent_demand_signals', 'int_so_what_box'): ex_intent_demand_signals__int_so_what_box,
    ('intent_demand_signals', 'int_bu_summary'): ex_intent_demand_signals__int_bu_summary,
    ('intent_demand_signals', 'int_bu_average'): ex_intent_demand_signals__int_bu_average,
    ('intent_demand_signals', 'int_bu_fallback'): ex_intent_demand_signals__int_bu_fallback,
    ('intent_demand_signals', 'int_bu_reads'): ex_intent_demand_signals__int_bu_reads,
    ('intent_demand_signals', 'hire_job_selection'): ex_intent_demand_signals__hire_job_selection,
    ('intent_demand_signals', 'hire_country_code'): ex_intent_demand_signals__hire_country_code,
    ('intent_demand_signals', 'hire_country_check'): ex_intent_demand_signals__hire_country_check,
    ('intent_demand_signals', 'hire_window'): ex_intent_demand_signals__hire_window,
    ('intent_demand_signals', 'hire_postings_tile'): ex_intent_demand_signals__hire_postings_tile,
    ('intent_demand_signals', 'hire_family_breakdown'): ex_intent_demand_signals__hire_family_breakdown,
    ('intent_demand_signals', 'hire_tech_tags'): ex_intent_demand_signals__hire_tech_tags,
    ('intent_demand_signals', 'hire_theme_assignment'): ex_intent_demand_signals__hire_theme_assignment,
    ('intent_demand_signals', 'hire_theme_cards'): ex_intent_demand_signals__hire_theme_cards,
    ('message_evaluator', 'me_scoring'): ex_message_evaluator__me_scoring,
    ('message_evaluator', 'me_score_bands'): ex_message_evaluator__me_score_bands,
    ('message_evaluator', 'me_dimension_validation'): ex_message_evaluator__me_dimension_validation,
    ('message_evaluator', 'me_severe_failures'): ex_message_evaluator__me_severe_failures,
    ('message_evaluator', 'me_scoring_context'): ex_message_evaluator__me_scoring_context,
    ('message_evaluator', 'me_structure_checks'): ex_message_evaluator__me_structure_checks,
    ('message_evaluator', 'me_claim_verdict'): ex_message_evaluator__me_claim_verdict,
    ('message_evaluator', 'me_phrase_feedback'): ex_message_evaluator__me_phrase_feedback,
    ('message_evaluator', 'me_chunk_fidelity'): ex_message_evaluator__me_chunk_fidelity,
    ('message_evaluator', 'me_reaction_guard'): ex_message_evaluator__me_reaction_guard,
    ('message_evaluator', 'me_cache_versions'): ex_message_evaluator__me_cache_versions,
    ('message_evaluator', 'me_rewrite_greeting'): ex_message_evaluator__me_rewrite_greeting,
    ('message_evaluator', 'me_rewrite_validation'): ex_message_evaluator__me_rewrite_validation,
    ('message_evaluator', 'me_rewrite_diff'): ex_message_evaluator__me_rewrite_diff,
    ('objection_playbook', 'technology_evidence_source'): ex_objection_playbook__technology_evidence_source,
    ('objection_playbook', 'vendor_token_matching'): ex_objection_playbook__vendor_token_matching,
    ('objection_playbook', 'area_evidence_string'): ex_objection_playbook__area_evidence_string,
    ('objection_playbook', 'topic_owner'): ex_objection_playbook__topic_owner,
    ('objection_playbook', 'topic_owner_wording'): ex_objection_playbook__topic_owner_wording,
    ('objection_playbook', 'rulebook_evidence_corpus'): ex_objection_playbook__rulebook_evidence_corpus,
    ('objection_playbook', 'rule_fired_by'): ex_objection_playbook__rule_fired_by,
    ('objection_playbook', 'qualifying_vs_indicative'): ex_objection_playbook__qualifying_vs_indicative,
    ('objection_playbook', 'family_gates'): ex_objection_playbook__family_gates,
    ('objection_playbook', 'rule_conditions'): ex_objection_playbook__rule_conditions,
    ('objection_playbook', 'area_to_rule_families'): ex_objection_playbook__area_to_rule_families,
    ('objection_playbook', 'fact_guardrails'): ex_objection_playbook__fact_guardrails,
    ('objection_playbook', 'proof_point'): ex_objection_playbook__proof_point,
    ('objection_playbook', 'proof_point_score'): ex_objection_playbook__proof_point_score,
    ('objection_playbook', 'sector_justification_check'): ex_objection_playbook__sector_justification_check,
    ('objection_playbook', 'hp_claim_faults'): ex_objection_playbook__hp_claim_faults,
    ('objection_playbook', 'superlative_country_case'): ex_objection_playbook__superlative_country_case,
    ('objection_playbook', 'merge_near_duplicates'): ex_objection_playbook__merge_near_duplicates,
    ('recent_news_signals', 'ls_sources'): ex_recent_news_signals__ls_sources,
    ('recent_news_signals', 'ls_headline_publisher'): ex_recent_news_signals__ls_headline_publisher,
    ('recent_news_signals', 'ls_duplicate_body'): ex_recent_news_signals__ls_duplicate_body,
    ('recent_news_signals', 'ls_category_map'): ex_recent_news_signals__ls_category_map,
    ('recent_news_signals', 'ls_gate'): ex_recent_news_signals__ls_gate,
    ('recent_news_signals', 'ls_dedup'): ex_recent_news_signals__ls_dedup,
    ('recent_news_signals', 'ls_score'): ex_recent_news_signals__ls_score,
    ('recent_news_signals', 'ls_recency'): ex_recent_news_signals__ls_recency,
    ('recent_news_signals', 'ls_source_reliability'): ex_recent_news_signals__ls_source_reliability,
    ('recent_news_signals', 'ls_source_first_party'): ex_recent_news_signals__ls_source_first_party,
    ('recent_news_signals', 'ls_source_aggregator'): ex_recent_news_signals__ls_source_aggregator,
    ('recent_news_signals', 'ls_source_structured'): ex_recent_news_signals__ls_source_structured,
    ('recent_news_signals', 'ls_source_unknown_fallback'): ex_recent_news_signals__ls_source_unknown_fallback,
    ('recent_news_signals', 'ls_source_line'): ex_recent_news_signals__ls_source_line,
    ('recent_news_signals', 'ls_no_tiers_no_floor_no_cap'): ex_recent_news_signals__ls_no_tiers_no_floor_no_cap,
    ('recent_news_signals', 'ls_angle_banned'): ex_recent_news_signals__ls_angle_banned,
    ('recent_news_signals', 'ls_angle_repetition'): ex_recent_news_signals__ls_angle_repetition,
    ('recent_news_signals', 'ls_angle_length'): ex_recent_news_signals__ls_angle_length,
    ('recent_news_signals', 'ls_hp_play'): ex_recent_news_signals__ls_hp_play,
    ('solution_narrative_opportunity_map', 'om_intent_timing_gate'): ex_solution_narrative_opportunity_map__om_intent_timing_gate,
    ('solution_narrative_opportunity_map', 'om_topic_kind'): ex_solution_narrative_opportunity_map__om_topic_kind,
    ('solution_narrative_opportunity_map', 'om_superseded_versions'): ex_solution_narrative_opportunity_map__om_superseded_versions,
    ('solution_narrative_opportunity_map', 'om_play_eligibility'): ex_solution_narrative_opportunity_map__om_play_eligibility,
    ('solution_narrative_opportunity_map', 'om_play_exclusions'): ex_solution_narrative_opportunity_map__om_play_exclusions,
    ('solution_narrative_opportunity_map', 'om_priority'): ex_solution_narrative_opportunity_map__om_priority,
    ('solution_narrative_opportunity_map', 'om_trigger_recency'): ex_solution_narrative_opportunity_map__om_trigger_recency,
    ('solution_narrative_opportunity_map', 'om_overclaim'): ex_solution_narrative_opportunity_map__om_overclaim,
    ('solution_narrative_opportunity_map', 'om_length_band'): ex_solution_narrative_opportunity_map__om_length_band,
    ('solution_narrative_opportunity_map', 'om_relevance_ladder'): ex_solution_narrative_opportunity_map__om_relevance_ladder,
    ('solution_narrative_opportunity_map', 'om_scale_statement'): ex_solution_narrative_opportunity_map__om_scale_statement,
    ('solution_narrative_opportunity_map', 'om_target_contacts'): ex_solution_narrative_opportunity_map__om_target_contacts,
    ('solution_narrative_opportunity_map', 'om_case_study_proof'): ex_solution_narrative_opportunity_map__om_case_study_proof,
    ('solution_narrative_opportunity_map', 'om_cs_canonical_line'): ex_solution_narrative_opportunity_map__om_cs_canonical_line,
    ('solution_narrative_opportunity_map', 'om_cs_ranking'): ex_solution_narrative_opportunity_map__om_cs_ranking,
    ('solution_narrative_opportunity_map', 'om_cs_industry'): ex_solution_narrative_opportunity_map__om_cs_industry,
    ('solution_narrative_opportunity_map', 'om_cs_allocation'): ex_solution_narrative_opportunity_map__om_cs_allocation,
    ('solution_narrative_opportunity_map', 'om_service_plays'): ex_solution_narrative_opportunity_map__om_service_plays,
    ('solution_narrative_opportunity_map', 'om_sp_matching'): ex_solution_narrative_opportunity_map__om_sp_matching,
    ('solution_narrative_opportunity_map', 'om_sp_conditions'): ex_solution_narrative_opportunity_map__om_sp_conditions,
    ('solution_narrative_opportunity_map', 'om_sp_iq_market'): ex_solution_narrative_opportunity_map__om_sp_iq_market,
    ('solution_narrative_opportunity_map', 'om_sp_selection'): ex_solution_narrative_opportunity_map__om_sp_selection,
    ('solution_narrative_opportunity_map', 'om_sp_confidential_facts'): ex_solution_narrative_opportunity_map__om_sp_confidential_facts,
    ('solution_narrative_opportunity_map', 'om_evidence_tier'): ex_solution_narrative_opportunity_map__om_evidence_tier,
    ('stakeholder_map', 'withhold_pending_review'): ex_stakeholder_map__withhold_pending_review,
    ('stakeholder_map', 'contact_field_precedence'): ex_stakeholder_map__contact_field_precedence,
    ('stakeholder_map', 'phone_normalisation'): ex_stakeholder_map__phone_normalisation,
    ('stakeholder_map', 'department_normalisation'): ex_stakeholder_map__department_normalisation,
    ('stakeholder_map', 'seniority_banding'): ex_stakeholder_map__seniority_banding,
    ('stakeholder_map', 'c_suite_corroboration'): ex_stakeholder_map__c_suite_corroboration,
    ('stakeholder_map', 'stakeholder_score'): ex_stakeholder_map__stakeholder_score,
    ('stakeholder_map', 'score_seniority'): ex_stakeholder_map__score_seniority,
    ('stakeholder_map', 'score_hp_relevance'): ex_stakeholder_map__score_hp_relevance,
    ('stakeholder_map', 'hp_relevance_department_text'): ex_stakeholder_map__hp_relevance_department_text,
    ('stakeholder_map', 'non_it_title_cap'): ex_stakeholder_map__non_it_title_cap,
    ('stakeholder_map', 'hp_relevance_band'): ex_stakeholder_map__hp_relevance_band,
    ('stakeholder_map', 'influence_type'): ex_stakeholder_map__influence_type,
    ('stakeholder_map', 'influence_substring_effects'): ex_stakeholder_map__influence_substring_effects,
    ('stakeholder_map', 'score_influence'): ex_stakeholder_map__score_influence,
    ('stakeholder_map', 'score_data_completeness'): ex_stakeholder_map__score_data_completeness,
    ('stakeholder_map', 'priority_level'): ex_stakeholder_map__priority_level,
    ('stakeholder_map', 'priority_contacts'): ex_stakeholder_map__priority_contacts,
    ('stakeholder_map', 'roster_order'): ex_stakeholder_map__roster_order,
    ('stakeholder_map', 'client_buying_committee_coverage'): ex_stakeholder_map__client_buying_committee_coverage,
    ('stakeholder_map', 'do_not_propose_list'): ex_stakeholder_map__do_not_propose_list,
    ('stakeholder_map', 'tp_grounding_check'): ex_stakeholder_map__tp_grounding_check,
    ('stakeholder_map', 'tp_decision_power_echo'): ex_stakeholder_map__tp_decision_power_echo,
    ('stakeholder_map', 'tp_no_hardware_override'): ex_stakeholder_map__tp_no_hardware_override,
    ('stakeholder_map', 'tp_pain_point_filter'): ex_stakeholder_map__tp_pain_point_filter,
    ('stakeholder_map', 'persona_role_match'): ex_stakeholder_map__persona_role_match,
    ('stakeholder_map', 'persona_ask_bounds'): ex_stakeholder_map__persona_ask_bounds,
    ('stakeholder_map', 'persona_line_eligibility'): ex_stakeholder_map__persona_line_eligibility,
    ('strategy_chat', 'sc_snapshot_widget'): ex_strategy_chat__sc_snapshot_widget,
    ('strategy_chat', 'sc_context_payload'): ex_strategy_chat__sc_context_payload,
    ('strategy_chat', 'sc_small_talk'): ex_strategy_chat__sc_small_talk,
    ('strategy_chat', 'sc_fact_check'): ex_strategy_chat__sc_fact_check,
    ('strategy_chat', 'sc_synthesis_check'): ex_strategy_chat__sc_synthesis_check,
    ('strategy_chat', 'sc_plan_figures'): ex_strategy_chat__sc_plan_figures,
    ('strategy_chat', 'sc_whole_answer_checks'): ex_strategy_chat__sc_whole_answer_checks,
    ('strategy_chat', 'sc_retry_partial'): ex_strategy_chat__sc_retry_partial,
    ('strategy_chat', 'sc_render'): ex_strategy_chat__sc_render,
    ('strategy_chat', 'sc_roleplay_personas'): ex_strategy_chat__sc_roleplay_personas,
    ('strategy_chat', 'sc_roleplay_validator'): ex_strategy_chat__sc_roleplay_validator,
    ('strategy_chat', 'sc_roleplay_starters'): ex_strategy_chat__sc_roleplay_starters,
    ('strategy_chat', 'sc_prose_validator'): ex_strategy_chat__sc_prose_validator,
    ('tech_landscape', 'tl_technology_sources'): ex_tech_landscape__tl_technology_sources,
    ('tech_landscape', 'tl_website_fallback'): ex_tech_landscape__tl_website_fallback,
    ('tech_landscape', 'tl_category_cards'): ex_tech_landscape__tl_category_cards,
    ('tech_landscape', 'tl_client_os_keywords'): ex_tech_landscape__tl_client_os_keywords,
    ('tech_landscape', 'tl_relationship_and_risk'): ex_tech_landscape__tl_relationship_and_risk,
    ('tech_landscape', 'tl_detection_status'): ex_tech_landscape__tl_detection_status,
    ('tech_landscape', 'tl_map_narrative'): ex_tech_landscape__tl_map_narrative,
    ('tech_landscape', 'tl_rulebook_offering_override'): ex_tech_landscape__tl_rulebook_offering_override,
    ('tech_landscape', 'tl_confidence_score'): ex_tech_landscape__tl_confidence_score,
    ('tech_landscape', 'tl_driver_1'): ex_tech_landscape__tl_driver_1,
    ('tech_landscape', 'tl_driver_1_route'): ex_tech_landscape__tl_driver_1_route,
    ('tech_landscape', 'tl_driver_1_related_family'): ex_tech_landscape__tl_driver_1_related_family,
    ('tech_landscape', 'tl_driver_1_card_fallback'): ex_tech_landscape__tl_driver_1_card_fallback,
    ('tech_landscape', 'tl_driver_2'): ex_tech_landscape__tl_driver_2,
    ('tech_landscape', 'tl_suppression_guardrail'): ex_tech_landscape__tl_suppression_guardrail,
    ('tech_landscape', 'tl_reconcile_after_suppression'): ex_tech_landscape__tl_reconcile_after_suppression,
    ('tech_landscape', 'tl_case_study_proof'): ex_tech_landscape__tl_case_study_proof,
    ('tech_landscape', 'tl_integration_routes'): ex_tech_landscape__tl_integration_routes,
    ('tech_landscape', 'tl_stack_matrix_groups'): ex_tech_landscape__tl_stack_matrix_groups,
    ('tech_landscape', 'tl_stack_view'): ex_tech_landscape__tl_stack_view,
    ('tech_landscape', 'tl_webstack_breakdown'): ex_tech_landscape__tl_webstack_breakdown,
    ('tech_landscape', 'tl_rec_evidence_corpus'): ex_tech_landscape__tl_rec_evidence_corpus,
    ('tech_landscape', 'tl_rec_rule_matching'): ex_tech_landscape__tl_rec_rule_matching,
    ('tech_landscape', 'tl_rec_selection'): ex_tech_landscape__tl_rec_selection,
    ('tech_landscape', 'tl_rec_part_a_placement'): ex_tech_landscape__tl_rec_part_a_placement,
    ('tech_landscape', 'tl_rec_part_b_cards'): ex_tech_landscape__tl_rec_part_b_cards,
    ('tech_landscape', 'tl_rec_lifecycle'): ex_tech_landscape__tl_rec_lifecycle,
    ('tech_landscape', 'tl_rec_fact_guardrails'): ex_tech_landscape__tl_rec_fact_guardrails,
    ('tech_landscape', 'tl_rec_confidence_band'): ex_tech_landscape__tl_rec_confidence_band,
    ('tech_landscape', 'tl_rec_evidence_tier'): ex_tech_landscape__tl_rec_evidence_tier,
    ('tech_landscape', 'tl_rec_llm_prose'): ex_tech_landscape__tl_rec_llm_prose,
}


def _verified():
    for key in rules_catalog.catalog_keys():
        for rule in rules_catalog._raw(key).get("rules") or []:
            if (rule.get("example") or {}).get("verified"):
                yield key, rule["id"]


def test_every_verified_example_has_a_computation():
    assert set(_verified()) == set(EXAMPLES)


def _expected(key, rule_id):
    for rule in rules_catalog._raw(key)["rules"]:
        if rule["id"] == rule_id:
            return rule["example"].get("expect", KeyError)
    raise KeyError(rule_id)


@pytest.mark.parametrize(("key", "rule_id"), sorted(EXAMPLES), ids=lambda v: str(v))
def test_example_matches_the_code(key, rule_id):
    live = rules_catalog._jsonable(EXAMPLES[(key, rule_id)]())
    if _CAPTURE:
        seen = {}
        if os.path.exists(_CAPTURE):
            with open(_CAPTURE) as handle:
                seen = json.load(handle)
        seen["%s.%s" % (key, rule_id)] = live
        with open(_CAPTURE, "w") as handle:
            json.dump(seen, handle)
        return
    stated = _expected(key, rule_id)
    assert stated is not KeyError, "%s.%s states no result" % (key, rule_id)
    stated = rules_catalog._jsonable(stated)
    assert rules_catalog._same(live, stated), "catalog says %r, code returns %r" % (stated, live)
