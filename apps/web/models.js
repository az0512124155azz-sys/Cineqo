// Cineqo model runtime bridge.
// app.js owns the UI. This file replaces CREATE-mode sending with the real
// Director -> Whisper -> Wan -> MuseTalk pipeline while leaving PLAN mode on /api/chat.

const sleep=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));

async function pollJson(path,{interval=5000,timeout=2*60*60*1000}={}){
  const started=Date.now();
  while(Date.now()-started<timeout){
    const r=await fetch(api(path));
    const d=await r.json();
    if(!r.ok) throw new Error(d.detail||`HTTP ${r.status}`);
    if(d.status==='succeeded'||d.status==='failed') return d;
    await sleep(interval);
  }
  throw new Error('Timed out waiting for model job');
}

function addProgress(title,text){
  const row=document.createElement('div');
  row.className='msgrow model-progress';
  row.innerHTML=`<div class="msg ai"><b>${title}</b><div class="model-progress-text"></div></div>`;
  row.querySelector('.model-progress-text').textContent=text;
  $('chat').appendChild(row);
  $('chat').scrollTop=$('chat').scrollHeight;
  return row.querySelector('.model-progress-text');
}

async function createWithModels(){
  const userPrompt=$('prompt').value.trim();
  if(!userPrompt&&!attachments.length) return;

  const hero=$('hero');if(hero)hero.remove();
  const files=[...attachments];
  const display=[userPrompt,...files.map(f=>`📎 ${f.name}`)].filter(Boolean).join('\n');
  addChat('user',display);
  $('prompt').value='';attachments=[];renderAttachments();

  const song=files.find(f=>f.type.startsWith('audio/'))||null;
  const image=files.find(f=>f.type.startsWith('image/'))||null;
  const progress=addProgress('Cineqo / CREATE',lang==='he'?'מכין את הבקשה ומפעיל את המודלים…':'Preparing the request and starting the models…');

  try{
    const fd=new FormData();
    fd.append('prompt',userPrompt||'Create a cinematic music video from the supplied material.');
    fd.append('language',lang);
    fd.append('artist_name',$('artistName').value||'');
    if(song)fd.append('song',song,song.name);
    if(image)fd.append('reference_image',image,image.name);

    const start=await fetch(api('/api/create'),{method:'POST',body:fd});
    const created=await start.json();
    if(!start.ok)throw new Error(created.detail||`HTTP ${start.status}`);

    if(created.transcription?.text){
      progress.textContent=lang==='he'?'Whisper תמלל את השיר. Wan 2.2 יוצר עכשיו את הווידאו…':'Whisper transcribed the track. Wan 2.2 is generating video…';
    }else{
      progress.textContent=lang==='he'?'Wan 2.2 יוצר עכשיו את הווידאו…':'Wan 2.2 is generating video…';
    }

    const video=await pollJson(`/api/video/jobs/${created.video_job.id}`);
    if(video.status!=='succeeded')throw new Error(video.error||video.stderr||'Wan generation failed');
    const videoPath=(video.files||[])[0];
    let finalJob=video;
    let finalType='Wan 2.2';

    if(song&&created.song_path&&videoPath){
      progress.textContent=lang==='he'?'הווידאו נוצר. MuseTalk מסנכרן עכשיו את השפתיים לשיר…':'Video created. MuseTalk is synchronizing lips to the track…';
      const lr=await fetch(api('/api/lipsync'),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({video_path:videoPath,audio_path:created.song_path})});
      const lj=await lr.json();
      if(!lr.ok)throw new Error(lj.detail||'Could not start lip-sync');
      finalJob=await pollJson(`/api/lipsync/jobs/${lj.id}`,{interval:4000,timeout:60*60*1000});
      if(finalJob.status!=='succeeded')throw new Error(finalJob.error||finalJob.stderr||'MuseTalk failed');
      finalType='Wan 2.2 + MuseTalk';
    }

    const urls=finalJob.file_urls||video.file_urls||[];
    progress.textContent=lang==='he'?`העיבוד הסתיים בהצלחה (${finalType}).`:`Finished successfully (${finalType}).`;
    if(urls.length){
      const a=document.createElement('a');
      a.href=api(urls[0]);a.target='_blank';a.rel='noopener';
      a.textContent=lang==='he'?'פתח את הווידאו שנוצר':'Open generated video';
      a.className='generated-file-link';
      progress.parentElement.appendChild(document.createElement('br'));
      progress.parentElement.appendChild(a);
    }
    conversation.push({role:'user',content:userPrompt});
    conversation.push({role:'assistant',content:`Generation completed with ${finalType}.`});
  }catch(e){
    progress.textContent=(lang==='he'?'שגיאת מנוע: ':'Model error: ')+(e.message||e);
  }
}

async function routedSend(){
  if(mode==='CREATE') return createWithModels();
  return sendChat();
}

async function showModelStatus(){
  try{
    const r=await fetch(api('/api/models/status'));
    const d=await r.json();
    window.cineqoModelStatus=d;
    document.documentElement.dataset.modelsReady=d.ready?'1':'0';
  }catch(e){
    window.cineqoModelStatus={ready:false,error:String(e)};
    document.documentElement.dataset.modelsReady='0';
  }
}

// Replace only the send bindings. Everything else remains owned by app.js.
$('sendButton').onclick=routedSend;
$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();routedSend()}};
showModelStatus();
