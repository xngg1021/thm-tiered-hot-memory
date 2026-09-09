"""Receipt-first compute/data plans over the existing complete-profile scheduler."""
from .segments import current
from thm.runtime.identity import digest

class ExecutionPlanner:
    def __init__(self,scheduler):self.scheduler=scheduler
    def plan(self,scope,*,workload='interactive',requested_profile=None):
        scheduler=self.scheduler
        with scheduler.lock:
            key=requested_profile or scheduler.choose(workload)
            if key not in scheduler.profiles or (scheduler.policy!='auto-throughput' and key!=scheduler.pinned):
                raise ValueError('runtime profile is pinned or unavailable')
            p=scheduler.profiles[key];index=scheduler.indexes[key]
        with index._lock:
            index.db.execute('BEGIN')
            try:
                row=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
                if not row:raise ValueError('scope missing')
                generation=row[0];count=len(index.rows(scope))
                complete=index.db.execute('SELECT generation,count FROM vector_generations WHERE scope=? AND profile=?',(scope,p.embedding_profile_id)).fetchone()
                if not complete or tuple(complete)!=(generation,count):raise ValueError('incomplete runtime profile generation')
                placement=current(index,scope,p.embedding_profile_id)
                if placement and (placement['generation']!=generation or placement['embedding_profile_id']!=p.embedding_profile_id):
                    raise ValueError('physical placement identity mismatch')
            finally:index.db.rollback()
        result={'schema':1,'scope_identity':digest(scope),'source_generation':generation,
            'semantic_policy':scheduler.policy,'runtime_profile_id':key,'embedding_profile_id':p.embedding_profile_id,
            'precision':p.precision,'lexical_index':'sqlite-local','vector_generation':generation,
            'representation':'immutable-segment' if placement else 'vectors_v2',
            'physical_target':placement['target_id'] if placement else 'sqlite-local',
            'matrix_read_path':placement['read_mode'] if placement else 'sqlite-buffered',
            'matrix_residency':'dram','encoder_device':p.device,'scorer':p.scorer,
            'scorer_device':p.device if p.scorer.startswith('torch') else 'cpu',
            'estimated_storage_bytes':placement['byte_length'] if placement else None,
            'transport':'filesystem-to-dram' if placement else 'sqlite-to-dram',
            'accelerator_copy_required':p.scorer.startswith('torch') and p.device!='cpu',
            'workload':workload,'fallback':'explicit-sparse' if scheduler.fallback else 'fail-closed',
            'automatic_relocation':False,'drift':'disclosed-by-runtime-profile; unmeasured' if scheduler.policy=='auto-throughput' else None}
        result['plan_id']=digest(result)
        return result
    def execute(self,plan,scope,query,**kwargs):
        actual=self.plan(scope,workload=plan['workload'],requested_profile=plan['runtime_profile_id'])
        if actual!=plan:raise ValueError('execution plan stale')
        result=self.scheduler.search(scope,query,workload=plan['workload'],requested_profile=plan['runtime_profile_id'],**kwargs)
        for item in result if isinstance(result,list) else [result]:
            if item.get('generation')!=plan['source_generation']:raise ValueError('generation changed during execution')
            item['execution_plan']=dict(plan)
            item['execution_plan']['actual_fallback']=item['runtime_receipt']['fallback_mode']
        return result
