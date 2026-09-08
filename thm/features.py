"""Default-off deterministic locators. No generated aliases, truth writes or hit events."""
from dataclasses import dataclass,asdict
from datetime import date
import re


@dataclass(frozen=True)
class RetrievalFeatures:
    entity: bool = False
    explicit_alias: bool = False
    temporal: bool = False
    query_grammar: bool = False
    segment: bool = False
    association: bool = False
    aliases: tuple = ()  # (explicit alias, exact canonical locator) pairs
    max_hops: int = 1
    max_neighbors: int = 4

    def __post_init__(self):
        for key in ('entity','explicit_alias','temporal','query_grammar','segment','association'):
            if type(getattr(self,key)) is not bool:raise ValueError('feature flags must be boolean')
        if type(self.max_hops) is not int or not 1<=self.max_hops<=2 or type(self.max_neighbors) is not int or not 1<=self.max_neighbors<=16:raise ValueError('bounded association settings required')
        if not isinstance(self.aliases,tuple) or len(self.aliases)>256:raise ValueError('bounded immutable aliases required')
        for pair in self.aliases:
            if not isinstance(pair,tuple) or len(pair)!=2 or any(not isinstance(v,str) or not v.strip() or len(v)>256 for v in pair):raise ValueError('explicit alias pair required')
    def identity(self):return asdict(self)
    @classmethod
    def parse(cls,value):
        if value is None:return cls()
        if isinstance(value,cls):return value
        if not isinstance(value,dict):raise ValueError('typed feature object required')
        data=dict(value)
        if 'aliases' in data:data['aliases']=tuple(tuple(p) for p in data['aliases'])
        return cls(**data)


@dataclass(frozen=True)
class QueryHints:
    kind: str | None = None
    temporal: str | None = None
    dates: tuple = ()
    conjunction: str | None = None
    operands: tuple = ()
    identifiers: tuple = ()
    months: tuple = ()
    date_precisions: tuple = ()


MONTHS={name:i for i,name in enumerate(('january','february','march','april','may','june','july','august','september','october','november','december'),1)}

def parse_query(query):
    if not isinstance(query,str) or len(query)>16000:return QueryHints()
    kind=re.match(r'^\s*(who|when|where|version)\b',query,re.I)
    temporal=re.search(r'\b(before|after|between|first|latest|previous|next|duration)\b',query,re.I)
    dates=[];precisions=[]
    for token in re.findall(r'\b(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?\b',query):
        try:
            parts=[int(x) for x in token.split('-')];stamp=date(*((parts+[1,1])[:3]));dates.append(stamp.isoformat());precisions.append(('year','month','day')[len(parts)-1])
        except ValueError:pass
    months=tuple(dict.fromkeys(MONTHS[m.group(0).lower()] for m in re.finditer(r'\b('+'|'.join(MONTHS)+r')\b',query,re.I)))
    for match in re.finditer(r'\b('+'|'.join(MONTHS)+r')\s+((?:19|20)\d{2})\b',query,re.I):
        year=int(match.group(2))
        retained=[(d,p) for d,p in zip(dates,precisions) if not (p=='year' and d==f'{year}-01-01')]
        dates=[d for d,p in retained];precisions=[p for d,p in retained]
        dates.append(date(year,MONTHS[match.group(1).lower()],1).isoformat());precisions.append('month')
    join=re.fullmatch(r'\s*(.{1,256}?)\s+(AND|OR)\s+(.{1,256}?)\s*',query)
    ids=tuple(re.findall(r'\b[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)+\b',query))
    return QueryHints(kind.group(1).upper() if kind else None,temporal.group(1).lower() if temporal else None,tuple(dates),
                      join.group(2) if join else None,(join.group(1),join.group(3)) if join else (),ids,months,tuple(precisions))


def timestamp(value):
    match=re.search(r'\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b',value)
    if match:
        try:return date(*map(int,match.groups()))
        except ValueError:pass
    match=re.search(r'\b(\d{1,2})\s+('+'|'.join(MONTHS)+r'),?\s+((?:19|20)\d{2})\b',value,re.I)
    if match:
        try:return date(int(match.group(3)),MONTHS[match.group(2).lower()],int(match.group(1)))
        except ValueError:pass
    return None


def contains(text,term):
    return re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I) is not None


class AliasIndex:
    """Scope-local derived locator lookup; supplied pairs express no durable truth."""
    def __init__(self,rows,pairs):
        self.entries=[]
        for row in rows:
            locators={row['speaker'],row['source'],row['id']}-{''}
            locators.update(re.findall(r'\b[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)+\b',row['text']))
            for alias,canonical in pairs:
                if canonical in locators:self.entries.append((alias,row['rowid']))
            for locator in locators:self.entries.append((locator,row['rowid']))
    def lookup(self,query,limit=100):
        return list(dict.fromkeys(rid for alias,rid in self.entries if contains(query,alias)))[:limit]


def reorder(rows,query,features):
    hints=parse_query(query)
    from .retrieval import terms,STOP
    query_terms=set(terms(query))-STOP
    def score(row):
        text=row['text'];lexical=bool(query_terms&set(terms(text)))
        grammar=0
        if features.query_grammar:
            if hints.conjunction=='AND':grammar=int(all(contains(text,t) for t in hints.operands))
            elif hints.conjunction=='OR':grammar=int(any(contains(text,t) for t in hints.operands))
            grammar+=sum(contains(text,i) for i in hints.identifiers)
        temporal_score=0;stamp=timestamp(row['timestamp'])
        if features.temporal and lexical and stamp:
            dates=[date.fromisoformat(d) for d in hints.dates]
            op=hints.temporal
            if op in ('before','previous') and len(dates)==1:temporal_score=int(stamp<dates[0])
            elif op in ('after','next') and len(dates)==1:temporal_score=int(stamp>dates[0])
            elif op=='between' and len(dates)==2:temporal_score=int(min(dates)<=stamp<=max(dates))
            elif dates:temporal_score=int(any(stamp.year==d.year and (precision=='year' or stamp.month==d.month) and (precision!='day' or stamp.day==d.day) for d,precision in zip(dates,hints.date_precisions)))
            elif hints.months:temporal_score=int(stamp.month in hints.months)
            elif op in ('first','latest'):temporal_score=stamp.toordinal()*(1 if op=='latest' else -1)
        active=features.temporal and (hints.temporal in ('first','latest','before','after','between','previous','next') or bool(hints.dates) or bool(hints.months))
        return grammar,int(bool(active and lexical and stamp)),temporal_score
    return sorted(rows,key=score,reverse=True)


def expand(rows,all_rows,features):
    selected=list(rows);seen={r['rowid'] for r in rows};frontier=list(rows);edges=[]
    for hop in range(features.max_hops):
        next_rows=[]
        for row in frontier:
            neighbors=[]
            for other in all_rows:
                if other['rowid'] in seen:continue
                relation=None
                if row['speaker'] and row['speaker']==other['speaker']:relation='same-explicit-speaker'
                elif row['source'] and row['source']==other['source']:relation='same-source'
                elif row['session']==other['session'] and abs(row['ord']-other['ord'])==1:relation='session-adjacency'
                elif contains(row['text'],other['id']):relation='explicit-identifier-reference'
                if relation:neighbors.append((other,relation))
            for other,relation in neighbors[:features.max_neighbors]:
                if len(edges)>=features.max_neighbors:break
                seen.add(other['rowid']);next_rows.append(other);edges.append({'from':row['id'],'to':other['id'],'relation':relation,'hop':hop+1})
            if len(edges)>=features.max_neighbors:break
        selected.extend(next_rows);frontier=next_rows
        if not frontier or len(edges)>=features.max_neighbors:break
    return selected,edges


def pack_segments(index,rows,budget,query):
    """Actual source slices; incomplete segments never inherit whole-parent credit."""
    from .retrieval import terms
    selected=[];blocks=[];used=0;query_terms=set(terms(query))
    for row in rows:
        context,full,count=index._pack_candidates([row],budget-used,query)
        # Recount joined text including separators using canonical counter.
        if full and index._count('\n\n'.join(blocks+[context]))<=budget:
            blocks.append(context);selected.extend(full);used=index._count('\n\n'.join(blocks));continue
        spans=[m.span() for m in re.finditer(r'[^\n.!?。！？]+[\n.!?。！？]*',row['text'])]
        spans.sort(key=lambda span:-len(query_terms&set(terms(row['text'][span[0]:span[1]]))))
        for begin,end in spans:
            if not query_terms&set(terms(row['text'][begin:end])):continue
            import json
            label='[segment '+json.dumps({'parent_id':row['id'],'start':begin,'end':end},ensure_ascii=False)+']\n'
            text=row['text'][begin:end];block=label+text
            if index._count('\n\n'.join(blocks+[block]))>budget:
                # Exact bounded character window around a lexical match, never fabricated text.
                hits=[m.start() for token in query_terms for m in re.finditer(re.escape(token),row['text'][begin:end],re.I)]
                if not hits:continue
                anchor=begin+min(hits);width=min(256,end-begin)
                while width>0:
                    lo=max(begin,anchor-width//4);hi=min(end,lo+width)
                    label='[segment '+json.dumps({'parent_id':row['id'],'start':lo,'end':hi},ensure_ascii=False)+']\n'
                    text=row['text'][lo:hi];block=label+text
                    if index._count('\n\n'.join(blocks+[block]))<=budget:
                        begin,end=lo,hi;break
                    width//=2
                if width==0:continue
            blocks.append(block);selected.append({'id':row['id'],'parent_id':row['id'],'hash':row['hash'],'source':row['source'],
                'complete':False,'text':text,'span_start':begin,'span_end':end,'locator_kind':'segment-v2'})
            used=index._count('\n\n'.join(blocks));break
    return '\n\n'.join(blocks),selected,used
