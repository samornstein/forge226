// Build an uncompressed ZIP using the spreadsheet package's UTF-8 XML parts.
function workbookZip(files) {
  const enc=new TextEncoder(), parts=[], directory=[];
  let offset=0;
  function header(size, fields) {
    const bytes=new Uint8Array(size), view=new DataView(bytes.buffer);
    for(const [position,width,value] of fields) view['setUint'+width](position,value,true);
    return bytes;
  }
  for(const [path,xml] of Object.entries(files)) {
    const name=enc.encode(path), data=enc.encode(xml);
    let crc=-1;
    for(const byte of data){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0)}
    crc=~crc;
    const local=header(30,[[0,32,0x04034b50],[4,16,20],[14,32,crc],[18,32,data.length],[22,32,data.length],[26,16,name.length]]);
    parts.push(local,name,data);
    directory.push(header(46,[[0,32,0x02014b50],[4,16,20],[6,16,20],[16,32,crc],[20,32,data.length],[24,32,data.length],[28,16,name.length],[42,32,offset]]),name);
    offset+=30+name.length+data.length;
  }
  const count=directory.length/2;
  return new Blob([...parts,...directory,header(22,[[0,32,0x06054b50],[8,16,count],[10,16,count],[12,32,directory.reduce((n,b)=>n+b.length,0)],[16,32,offset]])],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
function planWorkbook(plan) {
  const rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships', main='http://schemas.openxmlformats.org/spreadsheetml/2006/main';
  const xml=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const stepText=p=>p.label+' · '+p.time+' min'+(p.target?' · '+p.target:'');
  const rows=[['Date','Slot','Sport','Workout','Minutes','Phase','Intensity','Prescription','Purpose','Success cue','Alternative','Swim yards']];
  for(const x of [...plan.sessions].sort((a,b)=>a.date.localeCompare(b.date)||a.slot.localeCompare(b.slot))) rows.push([x.date,x.slot,x.sport,x.title,x.minutes,plan.trainingBlocks.find(b=>b.id===x.blockId)?.focus,x.intensity,[x.details,...(x.profileSteps||[]).map(stepText),...(x.optionalSteps?.length?['Optional version',...x.optionalSteps.map(stepText)]:[])].join('\n'),x.purpose,x.successCue,x.alternative,x.distanceYards]);
  const overview=[[plan.goal.name,'Season guide · Plan v'+plan.version],['Race day',plan.goal.raceDate],['Weekly volume','Hours cover planned endurance and active recovery. Strength follows the athlete’s time-accounting preference. Race time is excluded.'],['Workout calendar','Filter by date or sport. Times are minutes. Each row includes the prescription and execution cues.'],['Training phase','Dates and focus']];
  for(const block of plan.trainingBlocks) overview.push([block.focus,block.startDate+' to '+block.endDate+' — '+block.rationale]);
  const weeks=new Map();
  for(const x of plan.sessions){
    const day=new Date(x.date+'T00:00:00Z');
    day.setUTCDate(day.getUTCDate()-(day.getUTCDay()+6)%7);
    const key=day.toISOString().slice(0,10);
    const sums=weeks.get(key)||{};
    sums[x.sport]=(sums[x.sport]||0)+x.minutes;
    if(counted(x)){sums.required=(sums.required||0)+(x.baseMinutes??x.minutes);sums.upper=(sums.upper||0)+x.minutes;}
    weeks.set(key,sums);
  }
  const weekly=[['Week beginning','Required hours','With options (hours)','Swim min','Bike min','Run min','Other min','Strength min']];
  for(const [week,sums] of [...weeks].sort()){
    const minutes=['Swim','Bike','Run','Other'].map(k=>sums[k]||0);
    weekly.push([week,Number(((sums.required||0)/60).toFixed(2)),Number(((sums.upper||0)/60).toFixed(2)),...minutes,sums.Strength||0]);
  }
  const tabs=[
    {name:'Season guide',data:overview,widths:[44,95]},
    {name:'Weekly volume',data:weekly,widths:[20,20,22,14,14,14,14,17]},
    {name:'Workout calendar',data:rows,widths:[14,8,13,40,11,34,35,85,40,40,40,13]}
  ];
  const pkg='http://schemas.openxmlformats.org/package/2006';
  const mime='application/vnd.openxmlformats-officedocument.spreadsheetml.';
  const link=(id,type,target)=>'<Relationship Id="r'+id+'" Type="'+rel+'/'+type+'" Target="'+target+'"/>';
  const links=items=>'<Relationships xmlns="'+pkg+'/relationships">'+items+'</Relationships>';
  const override=(path,type)=>'<Override PartName="/xl/'+path+'" ContentType="'+mime+type+'+xml"/>';
  const files={
    '[Content_Types].xml':'<Types xmlns="'+pkg+'/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'+override('workbook.xml','sheet.main')+override('styles.xml','styles')+tabs.map((_,i)=>override('worksheets/sheet'+(i+1)+'.xml','worksheet')).join('')+'</Types>',
    '_rels/.rels':links(link(1,'officeDocument','xl/workbook.xml')),
    'xl/workbook.xml':'<workbook xmlns="'+main+'" xmlns:r="'+rel+'"><sheets>'+tabs.map((t,i)=>'<sheet name="'+t.name+'" sheetId="'+(i+1)+'" r:id="r'+(i+1)+'"/>').join('')+'</sheets></workbook>',
    'xl/_rels/workbook.xml.rels':links(tabs.map((_,i)=>link(i+1,'worksheet','worksheets/sheet'+(i+1)+'.xml')).join('')+link(4,'styles','styles.xml')),
    'xl/styles.xml':'<styleSheet xmlns="'+main+'"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF304D40"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf fontId="1" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs></styleSheet>'
  };
  tabs.forEach(({data,widths},i)=>{
    const body=data.map((row,n)=>'<row r="'+(n+1)+'">'+row.map((v,j)=>'<c r="'+String.fromCharCode(65+j)+(n+1)+'" s="'+(n===0||(i===0&&n===5)?1:0)+'" '+(typeof v==='number'?'><v>'+v+'</v>':'t="inlineStr"><is><t>'+xml(v)+'</t></is>')+'</c>').join('')+'</row>').join('');
    const cols=widths.map((w,j)=>'<col min="'+(j+1)+'" max="'+(j+1)+'" width="'+w+'" customWidth="1"/>').join('');
    const filter=i?'<autoFilter ref="A1:'+String.fromCharCode(64+widths.length)+data.length+'"/>':'';
    files['xl/worksheets/sheet'+(i+1)+'.xml']='<worksheet xmlns="'+main+'"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols>'+cols+'</cols><sheetData>'+body+'</sheetData>'+filter+'</worksheet>';
  });
  return workbookZip(files);
}
document.getElementById('export-plan').onclick=()=>{
 const url=URL.createObjectURL(planWorkbook(S)),a=document.createElement('a');
 a.href=url;a.download='Training-plan-v'+S.version+'.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
};
