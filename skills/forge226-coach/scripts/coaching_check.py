"""Validate the coaching record's structure, not the truth of its judgments."""
from datetime import date
import math


def validate_coaching(s):
    errors = []
    def need(condition, message):
        if not condition:
            errors.append(message)
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    def day(value):
        d = date.fromisoformat(value)
        if d.isoformat() != value:
            raise ValueError('Use YYYY-MM-DD')
        return d
    def num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0
    try:
        sessions = {x['id']: x for x in s.get('sessions', [])}
        seen, used = set(), set()
        for outcome in s.get('sessionOutcomes', []):
            ident = outcome['sessionId']
            need(ident in sessions and ident not in seen, 'Unknown or repeated outcome session')
            seen.add(ident)
            need(outcome.get('confirmed') is True and text(outcome.get('basis')), 'Session outcome needs confirmation and evidence basis')
            need(outcome.get('status') in ('completed', 'shortened', 'extended', 'substituted', 'missed-confirmed', 'unknown'), 'Invalid session outcome status')
            ids = outcome.get('activityIds', [])
            need(isinstance(ids, list) and all(text(x) for x in ids), 'Outcome activityIds must be a list of IDs')
            need(len(set(ids)) == len(ids) and not used.intersection(ids), 'An actual activity cannot complete multiple sessions')
            used.update(ids)
            if 'actualMinutes' in outcome:
                need(num(outcome['actualMinutes']), 'Invalid outcome minutes')
            if outcome.get('status') == 'missed-confirmed':
                need(not ids and outcome.get('actualMinutes', 0) == 0, 'Missed session cannot have completed minutes or activities')
        if 'coachingVersion' not in s:
            return errors  # Existing plans remain compatible.
        need(s['coachingVersion'] == 1, 'Unsupported coachingVersion')
        a = s['assessment']
        day(a['evidenceDate'])
        need(a.get('track') in ('completion', 'performance', 'qualification'), 'Invalid coaching track')
        need(a.get('feasibility') in ('supported', 'stretch', 'insufficient-evidence', 'reconsider'), 'Invalid goal feasibility')
        for key in ('baseline', 'goalDemands', 'rationale', 'nextAction'):
            need(text(a.get(key)), 'Assessment missing '+key)
        need(isinstance(a.get('uncertainties'), list), 'Assessment uncertainties must be a list')
        need(isinstance(a.get('priorities'), list) and 1 <= len(a['priorities']) <= 3 and all(text(x) for x in a['priorities']), 'Choose 1–3 assessment priorities')
        need(isinstance(a.get('disciplineExperience'), dict) and bool(a['disciplineExperience']), 'Assess experience by discipline')
        if a.get('track') == 'qualification':
            q = a['qualification']
            need(q.get('status') in ('verified', 'unverified'), 'Qualification status must be verified or unverified')
            need(text(q.get('timeGoalRelation')), 'Keep qualification separate from a time target')
            if q.get('status') == 'verified':
                for key in ('event', 'championshipYear', 'ageGroup', 'competitionCategory', 'rulesUrl', 'rulesSummary'):
                    need(bool(q.get(key)), 'Qualification missing '+key)
                day(q['checkedAt'])
            need(text(q.get('unknowns')), 'State qualification uncertainty, including future field and acceptance')
        blocks = s['trainingBlocks']
        need(isinstance(blocks, list) and bool(blocks), 'At least one measurable training block required')
        byid = {}
        for b in blocks:
            ident = b['id']
            need(text(ident) and ident not in byid, 'Invalid or repeated block ID')
            byid[ident] = b
            begin, end = day(b['startDate']), day(b['endDate'])
            need(day(s['goal']['startDate']) <= begin <= end <= day(s['goal']['endDate']), 'Block outside plan horizon')
            for key in ('focus', 'rationale', 'progressIf', 'repeatIf', 'reduceIf'):
                need(text(b.get(key)), 'Block missing '+key)
            checkpoints = b['checkpoints']
            need(isinstance(checkpoints, list) and bool(checkpoints), 'Block needs a checkpoint')
            for c in checkpoints:
                need(begin <= day(c['date']) <= end, 'Checkpoint outside block')
                for key in ('measure', 'criterion'):
                    need(text(c.get(key)), 'Checkpoint missing '+key)
                need(c.get('status') in ('planned', 'met', 'not-met', 'unknown'), 'Invalid checkpoint status')
                if c.get('status') in ('met', 'not-met'):
                    need(text(c.get('evidence')), 'Assessed checkpoint needs evidence')
        ordered = sorted(blocks, key=lambda b: b['startDate'])
        for previous, current in zip(ordered, ordered[1:]):
            need(previous['endDate'] < current['startDate'], 'Training blocks must not overlap')
        for row in sessions.values():
            if row['sport'] in ('Rest', 'Race'):
                continue
            b = byid.get(row.get('blockId'))
            need(b is not None, 'Training session needs a valid blockId: '+row['id'])
            if b:
                need(b['startDate'] <= row['date'] <= b['endDate'], 'Session outside its block: '+row['id'])
            if row.get('provisional') is not True:
                need(text(row.get('alternative')) and text(row.get('successCue')), 'Detailed session needs an alternative and success cue: '+row['id'])
        decisions = s['reviewDecisions']
        need(isinstance(decisions, list), 'reviewDecisions must be a list')
        if s.get('parentVersion') is not None:
            need(bool(decisions), 'A revision needs a saved review decision')
        for d in decisions:
            day(d['date']); day(d['nextReviewDate'])
            need(d['nextReviewDate'] > d['date'], 'Next review must follow decision date')
            need(d.get('action') in ('continue', 'progress', 'repeat', 'reduce', 'reschedule', 'pause', 'reassess'), 'Invalid review action')
            for key in ('evidence', 'reason', 'changes'):
                need(text(d.get(key)), 'Review decision missing '+key)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        errors.append('Malformed coaching record: '+str(exc))
    return errors
