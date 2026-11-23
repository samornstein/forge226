// Preview locally; saving uses the coach's version-checked draft workflow.
const initialSlots = new Map(rows.map(row=>[row.id,[row.date,row.slot]]));
function periodPriorities(){
 if(view==='day')return '';
 const start=mon(current), end=add(start,6);
 const selected=rows.filter(x=>(view==='month'?x.date.slice(0,7)===current.slice(0,7):start<=x.date&&x.date<=end)&&(!sport||sport===x.sport));
 const focuses=[...new Set(selected.map(x=>x.progressionFocus).filter(Boolean))];
 return focuses.length?'<p><b>Training focus</b> · '+focuses.map(esc).join(' · ')+'</p>':'';
}
function showPreview(){
 const changed=changedMoves().length>0;
 q('[data-request]').hidden=!changed;
 q('[data-reset]').hidden=!changed;
}
q('[data-reset]').onclick=()=>{
 for(const row of rows)[row.date,row.slot]=initialSlots.get(row.id);
 showPreview();render();
};
function progression(row){
 if(!row.progressionFocus)return '';
 const related=rows.filter(x=>x.progressionFocus===row.progressionFocus && x.sport===row.sport).sort((a,b)=>a.date.localeCompare(b.date));
 return '<details><summary>'+esc(row.progressionFocus)+' · progression</summary><ol>'+related.map(x=>'<li>'+esc(fmt(x.date)+' · '+x.title+(x.progressionNote?' · '+x.progressionNote:''))+'</li>').join('')+'</ol></details>';
}
function previewError(row,date,slot,proposed=rows){
 if(!date||!inPlan(date))return 'Choose a date within the plan.';
 const dayRows=proposed.filter(x=>x.date===date && x.id!==row.id);
 if(dayRows.some(x=>x.sport==='Rest'))return 'This is a planned rest day.';
 const day=fmt(date,{weekday:'long'}), exception=S.exceptions.find(e=>e.startDate<=date&&date<=e.endDate);
 const access=S.sportAccess?.[row.sport];
 if(access&&!access.includes(day+' '+slot))return 'This sport is unavailable in that slot.';
 if(exception?.allowedSports&&!exception.allowedSports.includes(row.sport))return 'This sport is unavailable during travel.';
 const limit=exception?.slots?.[slot]??S.availability?.[day]?.[slot];
 if(!limit?.enabled || total([...dayRows.filter(x=>x.slot===slot),row])>limit.minutes)return 'This exceeds slot availability.';
 if(exception?.maxMinutesPerDay!=null && total([...dayRows,row])>exception.maxMinutesPerDay)return 'This exceeds the daily cap.';
 const week=proposed.filter(x=>x.id!==row.id&&mon(x.date)===mon(date));
 if(S.weeklyCapMinutes!=null && total([...week,row])>S.weeklyCapMinutes)return 'This exceeds the weekly cap.';
 if(row.blockId && phase(date)?.id!==row.blockId)return 'Ask your coach about moving this workout across training phases.';
 if(row.date!==date && !proposed.some(x=>x.date===row.date && x.id!==row.id))return 'This would leave the original day empty. Ask your coach to revise both days.';
 return '';
}
function previewMove(row, date, slot, partner){
 if(partner===row)return '';
 const moves=[{row,date,slot}];
 if(partner)moves.push({row:partner,date:row.date,slot:row.slot});
 const proposed=rows.map(x=>{const edit=moves.find(m=>m.row===x);return edit?{...x,date:edit.date,slot:edit.slot}:x});
 const error=moves.map(m=>previewError(m.row,m.date,m.slot,proposed)).find(Boolean);
 if(error)return error;
 for(const edit of moves){edit.row.date=edit.date;edit.row.slot=edit.slot}
 q('dialog').close();move(date);showPreview();
 return '';
}
let dragged=null;
root.addEventListener('dragstart',event=>{
 const button=event.target.closest('[data-session][draggable="true"]');
 dragged=button?rows.find(x=>x.id===button.dataset.session):null;
 if(dragged)event.dataTransfer.setData('text/plain',dragged.id);
});
root.addEventListener('dragover',event=>{if(dragged&&event.target.closest('[data-drop-slot]'))event.preventDefault()});
root.addEventListener('drop',event=>{
 const slot=event.target.closest('[data-drop-slot]');
 if(!slot||!dragged)return;
 event.preventDefault();
 const partner=rows.find(x=>x.id===event.target.closest('[data-session]')?.dataset.session);
 const result=previewMove(dragged,slot.dataset.dropDate,slot.dataset.dropSlot,partner);
 q('[data-role="move-status"]').textContent=result||'Schedule preview updated.';
 dragged=null;
});
root.addEventListener('dragend',()=>{dragged=null});
root.addEventListener('click',event=>{
 const action=event.target.closest('[data-preview]');
 if(!action)return;
 const form=action.parentElement,row=rows.find(x=>x.id===action.dataset.preview);
 const partner=rows.find(x=>x.id===form.querySelector('[data-swap]').value);
 const date=partner?.date||form.querySelector('input').value,slot=partner?.slot||form.querySelector('[data-slot]').value;
 const error=previewMove(row,date,slot,partner);
 if(error)form.querySelector('output').textContent=error;
});
function changedMoves(){
 return rows.filter(row=>{const [d,t]=initialSlots.get(row.id);return d!==row.date||t!==row.slot}).map(({id,date,slot})=>({id,date,slot}));
}
function previewControls(row){
 if(!['AM','PM'].includes(row.slot))return '';
 return '<details><summary>Preview schedule change</summary><div><input aria-label="New date" type="date" value="'+esc(row.date)+'"><select data-slot aria-label="New slot">'+['AM','PM'].map(t=>'<option'+(row.slot===t?' selected':'')+'>'+t+'</option>').join('')+'</select><select data-swap aria-label="Swap with workout"><option value="">Move only</option>'+rows.filter(x=>x!==row && mon(x.date)===mon(row.date) && ['AM','PM'].includes(x.slot)).map(x=>'<option value="'+esc(x.id)+'">Swap with '+esc(fmt(x.date)+' '+x.slot+' '+x.title)+'</option>').join('')+'</select><button data-preview="'+esc(row.id)+'">Preview move</button><output role="status"></output></div></details>';
}
q('[data-request]').onclick=()=>{
 const request={goal:S.goal.name,version:S.version,scheduleKey:S.scheduleKey,moves:changedMoves()};
 const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(request,null,2)],{type:'application/json'}));
 a.href=url;a.download='schedule-request-v'+S.version+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
};
