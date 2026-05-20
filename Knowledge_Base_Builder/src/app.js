(function(){
  'use strict';
  var APP_VERSION='knowledge-center-v10';
  var STORAGE_KEY='kb_article_builder_v10';
  var INDEX_STORAGE_KEY='kb_article_index_v10';
  var bundledDefaultArticles=window.KB_DEFAULT_ARTICLES;
  var DEFAULT_ARTICLES=Array.isArray(bundledDefaultArticles)?bundledDefaultArticles:(bundledDefaultArticles?[bundledDefaultArticles]:[{
    id:'default-gateway-digital-signature',
    title:'Gateway Digital Signature',
    keywords:'EPA, signature, electronic signature, digital signature, end-point assessment, Microsoft Word',
    fileName:'gateway-digital-signature.html',
    path:'Articles/gateway-digital-signature.html',
    source:'articles-folder',
    sections:{
      inquiry:'Can we use the scribble function on Word to e-sign them?',
      summary:'',
      steps:'',
      resources:''
    },
    createdAt:'2026-05-12T17:39:35'
  }]);
  var sections=['inquiry','summary','steps','resources'];
  var attachments={inquiry:[],summary:[],steps:[],resources:[]};
  var knowledgeIndex=[];
  var editingArticle=null;
  var $=function(id){return document.getElementById(id)};
  var statusEl=$('status');

  function setStatus(msg,type){statusEl.textContent=msg;statusEl.className='status'+(type?' '+type:'')}
  function esc(v){return String(v == null ? '' : v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]})}
  function linkifyText(value){
    var text=String(value == null ? '' : value);
    var urlRe=/\bhttps?:\/\/[^\s<>"']+/gi;
    var html='',last=0,match;
    while((match=urlRe.exec(text))){
      var url=match[0],end=urlRe.lastIndex;
      while(/[.,;:!?)]$/.test(url)){
        url=url.slice(0,-1);
        end--;
      }
      html+=esc(text.slice(last,match.index));
      html+='<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(url)+'</a>';
      last=end;
      urlRe.lastIndex=end;
    }
    return html+esc(text.slice(last));
  }
  function safeName(name){return (String(name||'knowledge-base-article').trim().replace(/[^a-z0-9]+/gi,'-').replace(/^-+|-+$/g,'').toLowerCase()||'knowledge-base-article')}
  function safeFileName(name){return String(name||'attachment').split(/[\\/]/).pop().replace(/[^a-z0-9._-]+/gi,'-').replace(/^-+|-+$/g,'')||'attachment'}
  function uid(){return 'att_'+Math.random().toString(36).slice(2)+Date.now().toString(36)}
  function formatBytes(bytes){var n=Number(bytes||0);if(n<1024)return n+' B';if(n<1048576)return(n/1024).toFixed(1)+' KB';return(n/1048576).toFixed(1)+' MB'}
  function formatDate(value){var date=value?new Date(value):null;return date&&!isNaN(date.getTime())?date.toLocaleString():''}
  function getArticleCreatedAt(data){return data&&data.createdAt||data&&data.exportedAt||new Date().toISOString()}
  function getArticleUpdatedAt(data){return data&&data.updatedAt||data&&data.editedAt||''}
  function readText(file){return new Promise(function(res,rej){var r=new FileReader();r.onload=function(){res(r.result)};r.onerror=function(){rej(r.error||new Error('Failed to read file'))};r.readAsText(file)})}
  function readDataUrl(file){return new Promise(function(res,rej){var r=new FileReader();r.onload=function(){res(r.result)};r.onerror=function(){rej(r.error||new Error('Failed to read file'))};r.readAsDataURL(file)})}

  function getArticleData(){
    var existing=editingArticle&&editingArticle.data?editingArticle.data:{};
    var now=new Date().toISOString();
    var data={schema:'kb-article-builder',version:APP_VERSION,createdAt:getArticleCreatedAt(existing),updatedAt:editingArticle?now:getArticleUpdatedAt(existing),title:$('title').value||'Untitled article',keywords:$('keywords').value||'',sections:{},attachments:JSON.parse(JSON.stringify(attachments))};
    sections.forEach(function(s){data.sections[s]=$(s+'Text').value||''});
    return data;
  }
  function normalizeArticleData(data){
    if(!data||typeof data!=='object')throw new Error('The selected file does not contain valid article data.');
    var normal={schema:'kb-article-builder',version:data.version||APP_VERSION,createdAt:getArticleCreatedAt(data),updatedAt:getArticleUpdatedAt(data),title:data.title||data.articleTitle||'Untitled article',keywords:data.keywords||'',sections:{},attachments:{inquiry:[],summary:[],steps:[],resources:[]}};
    sections.forEach(function(s){normal.sections[s]=(data.sections&&data.sections[s])||data[s]||'';normal.attachments[s]=(data.attachments&&Array.isArray(data.attachments[s]))?data.attachments[s]:[]});
    return normal;
  }
  function resetArticleForm(){
    editingArticle=null;
    $('title').value='';
    $('keywords').value='';
    sections.forEach(function(s){$(s+'Text').value='';attachments[s]=[]});
    renderAttachmentBoxes();
  }
  function loadArticleData(data,sourceItem){
    var normal=normalizeArticleData(data);
    editingArticle=sourceItem?{id:sourceItem.id||'',fileName:sourceItem.fileName||'',path:sourceItem.path||'',data:normal}:null;
    $('title').value=normal.title||'';$('keywords').value=normal.keywords||'';
    sections.forEach(function(s){$(s+'Text').value=normal.sections[s]||'';attachments[s]=normal.attachments[s]||[]});
    renderAttachmentBoxes();setBuilderView();setStatus('Article opened for editing.','ok');
  }
  function parseJson(raw){try{return JSON.parse(String(raw||'').replace(/^\uFEFF/,'').trim())}catch(e){throw new Error('The file could not be parsed as article JSON. '+e.message)}}
  function parseArticleFromHtml(html){
    var doc=new DOMParser().parseFromString(String(html),'text/html');
    var tpl=doc.getElementById('kb-article-json');
    if(tpl)return parseJson(tpl.textContent||tpl.innerHTML||'');
    var script=doc.querySelector('script[type="application/json"][data-kb-article],script#kb-article-data');
    if(script)return parseJson(script.textContent||'');
    throw new Error('This HTML file is not a valid exported article from this builder.');
  }
  function parseArticleContent(text,fileName){
    var clean=String(text||'').replace(/^\uFEFF/,'').trim();
    var lower=String(fileName||'').toLowerCase();
    if(lower.endsWith('.html')||lower.endsWith('.htm')||/^<!doctype html|^<html[\s>]/i.test(clean)||clean.indexOf('kb-article-json')>-1)return normalizeArticleData(parseArticleFromHtml(clean));
    return normalizeArticleData(parseJson(clean));
  }

  function attachmentBoxHtml(section){
    return '<div class="attachment-head"><div><strong>Attachments for this section</strong><p class="hint">Drag files here, paste screenshots, or add a link.</p></div><div class="toolbar"><input class="hidden-input" type="file" id="file_'+section+'" multiple><button class="small" data-action="pick" type="button">Add files</button><button class="small" data-action="link" type="button">Add link</button></div></div><div class="attachment-list" id="list_'+section+'"></div>';
  }
  function renderAttachmentBoxes(){document.querySelectorAll('.attachment-box').forEach(function(box){var section=box.getAttribute('data-attach'),fresh=box.cloneNode(false);box.parentNode.replaceChild(fresh,box);fresh.innerHTML=attachmentBoxHtml(section);bindAttachmentBox(fresh,section);renderAttachmentList(section)})}
  function renderAttachmentList(section){
    var list=$('list_'+section),items=attachments[section]||[];
    if(!items.length){list.innerHTML='<p class="hint">No attachments added yet.</p>';return}
    list.innerHTML=items.map(function(att){
      var src=att.evidencePath||att.url||att.dataUrl||'';
      var isImg=String(att.type||'').indexOf('image/')===0||String(src).match(/\.(png|jpe?g|gif|webp|svg)$/i)||String(src).indexOf('data:image/')===0;
      var thumb=isImg&&src?'<img class="thumb" alt="'+esc(att.name)+'" src="'+esc(src)+'">':'<div class="thumb">File</div>';
      return '<div class="attachment-item"><div>'+thumb+'</div><div><div class="att-name">'+esc(att.name||att.url||att.evidencePath||'Attachment')+'</div><div class="att-meta">'+esc(att.type||'link')+(att.size?' - '+formatBytes(att.size):'')+(att.evidencePath?' | '+esc(att.evidencePath):'')+'</div></div><div class="att-actions"><button class="small" data-action="open" data-section="'+section+'" data-id="'+esc(att.id)+'" type="button">Open</button>'+(att.dataUrl?'<button class="small" data-action="download" data-section="'+section+'" data-id="'+esc(att.id)+'" type="button">Download</button>':'')+'<button class="small danger" data-action="remove" data-section="'+section+'" data-id="'+esc(att.id)+'" type="button">Remove</button></div></div>';
    }).join('');
  }
  function bindAttachmentBox(box,section){
    var input=box.querySelector('#file_'+section);
    box.addEventListener('click',function(e){var btn=e.target.closest('button');if(!btn)return;var action=btn.getAttribute('data-action'),id=btn.getAttribute('data-id');if(action==='pick')input.click();if(action==='link'){var url=prompt('Paste attachment or source link:');if(url){attachments[section].push({id:uid(),name:url,type:'link',url:url});renderAttachmentList(section)}}if(action==='open')openAttachment(section,id);if(action==='download')downloadAttachment(section,id);if(action==='remove'){attachments[section]=attachments[section].filter(function(a){return a.id!==id});renderAttachmentList(section)}});
    input.addEventListener('change',function(){addFiles(section,input.files).then(function(){input.value=''})});
    box.tabIndex=0;
    box.addEventListener('paste',function(e){var files=Array.from((e.clipboardData&&e.clipboardData.files)||[]);if(files.length){e.preventDefault();addFiles(section,files)}});
    ['dragenter','dragover'].forEach(function(ev){box.addEventListener(ev,function(e){e.preventDefault();box.classList.add('drag')})});
    ['dragleave','drop'].forEach(function(ev){box.addEventListener(ev,function(e){e.preventDefault();box.classList.remove('drag')})});
    box.addEventListener('drop',function(e){addFiles(section,e.dataTransfer.files)});
  }
  function addFiles(section,fileList){return Promise.all(Array.from(fileList||[]).map(function(file){return readDataUrl(file).then(function(dataUrl){var name=safeFileName(file.name);attachments[section].push({id:uid(),name:name,type:file.type||'application/octet-stream',size:file.size,evidencePath:'Evidence/'+name,dataUrl:dataUrl})})})).then(function(){renderAttachmentList(section);setStatus('Attachment added to '+section+'. It will be stored in Evidence when the article is saved.','ok')})}
  function findAtt(section,id){return (attachments[section]||[]).find(function(a){return a.id===id})}
  function openAttachment(section,id){var att=findAtt(section,id);if(!att)return;var src=att.evidencePath||att.url||att.dataUrl;if(src)window.open(src,'_blank','noopener,noreferrer')}
  function downloadAttachment(section,id){var att=findAtt(section,id);if(!att||!att.dataUrl)return;var a=document.createElement('a');a.href=att.dataUrl;a.download=att.name||'attachment';document.body.appendChild(a);a.click();a.remove()}

  function resolveAttachmentSrc(src,assetBase){
    src=String(src||'');
    if(!src)return '';
    if(/^(https?:|data:|blob:)/i.test(src))return src;
    if(assetBase&&src.indexOf('Evidence/')===0)return assetBase.replace(/\/?$/,'/')+src;
    if(src.indexOf('Evidence/')===0)return '../'+src;
    return src;
  }
  function staticAttachmentHtml(att,assetBase){
    var src=att.evidencePath||att.url||att.dataUrl||'';
    src=resolveAttachmentSrc(src,assetBase);
    var isImg=String(att.type||'').indexOf('image/')===0||String(src).match(/\.(png|jpe?g|gif|webp|svg)$/i)||String(src).indexOf('data:image/')===0;
    if(isImg&&src){
      var frameDoc='<!doctype html><html><head><meta charset="utf-8"><style>html,body{width:100%;height:100%;margin:0;background:#f8fafc}body{display:grid;place-items:center;overflow:hidden}img{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain}</style></head><body><img src="'+esc(src)+'" alt="'+esc(att.name||'Image attachment')+'"></body></html>';
      return '<details class="image-attachment" open><summary>'+esc(att.name||'Image attachment')+'</summary><iframe class="image-frame" srcdoc="'+esc(frameDoc)+'" title="'+esc(att.name||'Image attachment')+'"></iframe><div class="att-actions"><a class="file-btn small" href="'+esc(src)+'" target="_blank" rel="noopener noreferrer">Open</a>'+(att.dataUrl?'<a class="file-btn small" href="'+att.dataUrl+'" download="'+esc(att.name||'attachment')+'">Download</a>':'')+'</div></details>';
    }
    var thumb=isImg&&src?'<img class="thumb" alt="'+esc(att.name)+'" src="'+esc(src)+'">':'<div class="thumb">File</div>';
    var open=src||'#';
    return '<div class="attachment-item">'+thumb+'<div><div class="att-name">'+esc(att.name||att.url||'Attachment')+'</div><div class="att-meta">'+esc(att.type||'link')+(att.size?' - '+formatBytes(att.size):'')+'</div></div><div class="att-actions"><a class="file-btn small" href="'+esc(open)+'" target="_blank" rel="noopener noreferrer">Open</a>'+(att.dataUrl?'<a class="file-btn small" href="'+att.dataUrl+'" download="'+esc(att.name||'attachment')+'">Download</a>':'')+'</div></div>';
  }
  function getAppStyles(){
    var css='';
    Array.from(document.styleSheets).forEach(function(sheet){
      try{
        css+=Array.from(sheet.cssRules||[]).map(function(rule){return rule.cssText}).join('\n')+'\n';
      }catch(e){}
    });
    return css||'body{font-family:Arial,Helvetica,sans-serif;margin:0;background:#f6f7fb;color:#172033}.static-body{max-width:980px;margin:28px auto 60px;padding:0 18px}.static-top,.static-section{background:#fff;border:1px solid #d9e0ec;border-radius:18px;padding:24px;margin-bottom:16px}.static-content{white-space:pre-wrap;line-height:1.6}.static-content a{color:#5b3f8c;font-weight:700;overflow-wrap:anywhere}.image-frame{width:100%;height:min(70vh,720px);min-height:420px;border:1px solid #d9e0ec;border-radius:12px}';
  }
  function createStaticHtml(data,options){
    var labels={inquiry:'Inquiry',summary:'Summary',steps:'Steps',resources:'Resources'};
    var assetBase=options&&options.assetBase;
    var style=getAppStyles();
    var json=esc(JSON.stringify(data));
    var created=formatDate(data.createdAt||data.exportedAt)||formatDate(Date.now());
    var updated=formatDate(data.updatedAt||data.editedAt);
    var dateHtml='<p class="hint">Created: '+esc(created)+'</p>'+(updated?'<p class="hint">Edited: '+esc(updated)+'</p>':'');
    var sectionHtml=sections.map(function(s,i){var atts=(data.attachments&&data.attachments[s])||[];return '<section class="static-section"><h2>'+(i+1)+'. '+labels[s]+'</h2><div class="static-content">'+linkifyText((data.sections||{})[s]||'')+'</div><h3>Attachments</h3><div class="static-att-grid">'+(atts.length?atts.map(function(att){return staticAttachmentHtml(att,assetBase)}).join(''):'<p class="hint">No attachments added.</p>')+'</div></section>'}).join('');
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(data.title||'Knowledge Base Article')+'</title><style>'+style+'</style></head><body><div class="static-body"><div class="static-top"><span class="badge">Knowledge Base Article</span><h1>'+esc(data.title||'Untitled article')+'</h1><p class="subtitle"><strong>Keywords:</strong> '+esc(data.keywords||'')+'</p>'+dateHtml+'</div>'+sectionHtml+'</div><template id="kb-article-json">'+json+'</template></body></html>';
  }
  function prepareArticleForSave(data){
    var clean=JSON.parse(JSON.stringify(data));
    sections.forEach(function(section){
      clean.attachments[section]=(clean.attachments[section]||[]).map(function(att){
        if(att.dataUrl&&!att.evidencePath&&!att.url)att.evidencePath='Evidence/'+safeFileName(att.name||'attachment');
        return att;
      });
    });
    return clean;
  }
  function stripEmbeddedAttachmentData(data){
    var clean=JSON.parse(JSON.stringify(data));
    sections.forEach(function(section){
      clean.attachments[section]=(clean.attachments[section]||[]).map(function(att){
        if(att.evidencePath)delete att.dataUrl;
        return att;
      });
    });
    return clean;
  }
  function chooseArticleFilename(data){
    if(editingArticle&&editingArticle.fileName)return editingArticle.fileName;
    var base=safeName(data.title);
    var filename=base+'.html';
    var n=2;
    while(knowledgeIndex.some(function(item){return String(item.fileName||'').toLowerCase()===filename.toLowerCase()})){
      filename=base+'-'+n+'.html';
      n++;
    }
    return filename;
  }
  function blobDownload(blob,filename){var url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url)},1500)}
  function saveFile(html,filename,data){
    var evidence=[];
    sections.forEach(function(section){(data.attachments[section]||[]).forEach(function(att){if(att.dataUrl&&att.evidencePath)evidence.push({name:att.evidencePath.replace(/^Evidence\//,''),dataUrl:att.dataUrl})})});
    if(window.location.protocol!=='file:'){
      return fetch('/api/articles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:filename,html:html,evidence:evidence})}).then(function(res){return res.json().then(function(body){if(!res.ok||!body.ok)throw new Error(body.error||'Article save failed.');return body})}).then(function(){setStatus('Saved article to Articles/'+filename+' and attachments to Evidence.','ok')}).catch(function(e){blobDownload(new Blob([html],{type:'text/html;charset=utf-8'}),filename);setStatus((e&&e.message?e.message+' ':'')+'Downloaded article instead. Run with npm start to save directly into Articles.','err')});
    }
    blobDownload(new Blob([html],{type:'text/html;charset=utf-8'}),filename);
    setStatus('Downloaded article: '+filename+'. Run with npm start to save directly into Articles.','ok');
    return Promise.resolve();
  }
  function saveCurrentArticle(){
    var data=prepareArticleForSave(getArticleData());
    var storedData=stripEmbeddedAttachmentData(data);
    var filename=chooseArticleFilename(data);
    var html=createStaticHtml(storedData);
    return saveFile(html,filename,data).then(function(){
      editingArticle={id:editingArticle&&editingArticle.id?editingArticle.id:uid(),fileName:filename,path:'Articles/'+filename,data:storedData};
      addOrReplaceIndexItem({id:editingArticle.id,title:storedData.title,keywords:storedData.keywords,fileName:filename,path:editingArticle.path,source:'articles-folder',html:html,json:JSON.stringify(storedData),sections:storedData.sections,attachments:storedData.attachments,createdAt:storedData.createdAt,updatedAt:storedData.updatedAt});
      renderKnowledgeResults();
    });
  }
  function setClearEnabled(enabled){$('clearBtn').disabled=!enabled}
  function setActiveTab(tabId){$('knowledgeTab').classList.toggle('active',tabId==='knowledgeTab');$('creationTab').classList.toggle('active',tabId==='creationTab')}
  function setToolsMenuVisible(visible){$('appMain').classList.toggle('tools-hidden',!visible);$('toolsMenu').setAttribute('aria-hidden',String(!visible))}
  function setBuilderView(){document.querySelectorAll('.view').forEach(function(v){v.classList.remove('active')});$('builderView').classList.add('active');setActiveTab('creationTab');setToolsMenuVisible(true);setClearEnabled(true)}
  function setCenterView(){document.querySelectorAll('.view').forEach(function(v){v.classList.remove('active')});$('centerView').classList.add('active');setActiveTab('knowledgeTab');setToolsMenuVisible(false);setClearEnabled(false);renderKnowledgeResults()}
  function articleSearchText(article){var parts=[article.title,article.keywords,article.fileName];sections.forEach(function(s){parts.push(article.sections&&article.sections[s]||'')});return parts.join(' ').toLowerCase()}
  function saveKnowledgeIndex(){try{localStorage.setItem(INDEX_STORAGE_KEY,JSON.stringify(knowledgeIndex))}catch(e){setStatus('Knowledge index is too large to save in browser storage. Search still works for this session.','err')}}
  function seedDefaultArticles(){
    DEFAULT_ARTICLES.forEach(function(item){
      var existing=knowledgeIndex.findIndex(function(a){return a.id===item.id||String(a.fileName||'').toLowerCase()===item.fileName.toLowerCase()});
      if(existing>=0){
        knowledgeIndex[existing]=item;
      }else{
        knowledgeIndex.push(item);
      }
    });
  }
  function loadArticlesFolderIndex(){
    if(window.location.protocol==='file:')return Promise.resolve();
    return fetch('/api/articles',{cache:'no-store'}).then(function(res){
      return res.json().then(function(body){if(!res.ok||!body.ok)throw new Error(body.error||'Could not read Articles folder.');return body});
    }).then(function(body){
      knowledgeIndex=knowledgeIndex.filter(function(item){return item.source!=='articles-folder'});
      (body.articles||[]).forEach(function(item){addOrReplaceIndexItem(item)});
      updateIndexCount();
      saveKnowledgeIndex();
      renderKnowledgeResults();
    }).catch(function(e){
      setStatus((e&&e.message?e.message:'Could not read Articles folder.')+' Showing browser index only.','err');
    });
  }
  function loadKnowledgeIndex(){try{knowledgeIndex=JSON.parse(localStorage.getItem(INDEX_STORAGE_KEY)||'[]')}catch(e){knowledgeIndex=[]}seedDefaultArticles();updateIndexCount();saveKnowledgeIndex();loadArticlesFolderIndex()}
  function updateIndexCount(){$('indexCount').textContent=knowledgeIndex.length+' article'+(knowledgeIndex.length===1?'':'s')+' indexed'}
  function addOrReplaceIndexItem(item){var key=String(item.fileName||item.title||item.id).toLowerCase();var existing=knowledgeIndex.findIndex(function(x){return String(x.fileName||x.title||x.id).toLowerCase()===key});if(existing>=0)knowledgeIndex[existing]=item;else knowledgeIndex.push(item);updateIndexCount();saveKnowledgeIndex()}
  function indexFileObject(file){return readText(file).then(function(text){var article=parseArticleContent(text,file.name);var lower=file.name.toLowerCase(),isHtml=lower.endsWith('.html')||lower.endsWith('.htm')||/^\s*<!doctype html|^\s*<html[\s>]/i.test(text);addOrReplaceIndexItem({id:uid(),title:article.title,keywords:article.keywords,fileName:file.name,source:'file',html:isHtml?text:createStaticHtml(article),json:JSON.stringify(article),sections:article.sections,createdAt:article.createdAt,updatedAt:article.updatedAt})})}
  function editableDataFromIndexItem(item){
    return normalizeArticleData({title:item.title,keywords:item.keywords,sections:item.sections||{},attachments:item.attachments||{},createdAt:item.createdAt,updatedAt:item.updatedAt,exportedAt:item.exportedAt});
  }
  function loadIndexedArticleForEditing(item){
    if(item.json)return Promise.resolve(normalizeArticleData(JSON.parse(item.json)));
    if(item.html)return Promise.resolve(parseArticleContent(item.html,item.fileName||'article.html'));
    if(item.path&&window.location.protocol!=='file:'){
      return fetch(item.path,{cache:'no-store'}).then(function(res){
        if(!res.ok)throw new Error('Could not read '+item.fileName+' from the Articles folder.');
        return res.text();
      }).then(function(text){
        var article=parseArticleContent(text,item.fileName||item.path);
        item.html=text;
        item.json=JSON.stringify(article);
        item.sections=article.sections;
        item.keywords=article.keywords;
        item.title=article.title;
        item.createdAt=article.createdAt;
        item.updatedAt=article.updatedAt;
        addOrReplaceIndexItem(item);
        return article;
      });
    }
    return Promise.resolve(editableDataFromIndexItem(item));
  }
  function renderKnowledgeResults(){
    var q=($('knowledgeSearch').value||'').trim().toLowerCase(),words=q.split(/\s+/).filter(Boolean),results=knowledgeIndex.slice();
    if(words.length)results=results.filter(function(a){var txt=articleSearchText(a);return words.every(function(w){return txt.indexOf(w)>-1})});
    results.sort(function(a,b){return String(a.title||'').localeCompare(String(b.title||''))});
    var box=$('knowledgeResults');
    if(!results.length){box.innerHTML='<p class="hint">No matching articles found.</p>';return}
    box.innerHTML=results.map(function(a){var created=formatDate(a.createdAt||a.exportedAt),updated=formatDate(a.updatedAt||a.editedAt);return '<div class="article-result"><div><h3>'+esc(a.title||'Untitled article')+'</h3><p class="muted"><strong>Keywords:</strong> '+esc(a.keywords||'No keywords')+'</p><p class="hint">'+esc(a.fileName||'Indexed article')+(created?' | Created: '+esc(created):'')+(updated?' | Edited: '+esc(updated):'')+'</p></div><div class="result-actions"><button class="small primary" data-kb-action="open" data-id="'+esc(a.id)+'" type="button">Open</button><button class="small" data-kb-action="edit" data-id="'+esc(a.id)+'" type="button">Edit</button><button class="small danger" data-kb-action="remove" data-id="'+esc(a.id)+'" type="button">Remove</button></div></div>'}).join('');
  }
  function findIndexed(id){return knowledgeIndex.find(function(a){return a.id===id})}
  function openArticleHtml(html){var url=URL.createObjectURL(new Blob([html],{type:'text/html'}));window.open(url,'_blank','noopener,noreferrer');setTimeout(function(){URL.revokeObjectURL(url)},60000)}
  function openIndexedArticle(id){
    var a=findIndexed(id);
    if(!a)return;
    var previewOptions={assetBase:window.location.origin+'/'};
    if(a.json){openArticleHtml(createStaticHtml(normalizeArticleData(JSON.parse(a.json)),previewOptions));return}
    if(a.html){openArticleHtml(createStaticHtml(parseArticleContent(a.html,a.fileName||'article.html'),previewOptions));return}
    if(a.path&&window.location.protocol!=='file:'){
      fetch(a.path,{cache:'no-store'}).then(function(res){
        if(!res.ok)throw new Error('Could not read '+(a.fileName||'the article')+' from the Articles folder.');
        return res.text();
      }).then(function(text){
        openArticleHtml(createStaticHtml(parseArticleContent(text,a.fileName||a.path),previewOptions));
      }).catch(function(){window.open(a.path,'_blank','noopener,noreferrer')});
      return;
    }
  }
  function editIndexedArticle(id){var a=findIndexed(id);if(!a)return;loadIndexedArticleForEditing(a).then(function(data){loadArticleData(data,a)}).catch(function(e){loadArticleData(editableDataFromIndexItem(a),a);setStatus((e&&e.message?e.message+' ':'')+'Opened the indexed article fields for editing. Add the article file to include embedded attachments.','err')})}
  function removeFromLocalIndex(id,message,type){
    knowledgeIndex=knowledgeIndex.filter(function(a){return a.id!==id});
    saveKnowledgeIndex();
    updateIndexCount();
    renderKnowledgeResults();
    setStatus(message,type||'ok');
  }
  function removeIndexedArticle(id){
    var article=findIndexed(id);
    if(!article)return;
    if(window.location.protocol!=='file:'&&article.source==='articles-folder'&&article.fileName){
      setStatus('Moving article to Articles/Bin...','ok');
      return fetch('/api/articles',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:article.fileName})}).then(function(res){
        return res.json().then(function(body){if(!res.ok||!body.ok)throw new Error(body.error||'Article removal failed.');return body});
      }).then(function(body){
        removeFromLocalIndex(id,'Article moved to '+(body.path||'Articles/Bin')+' and removed from the Knowledge Center.','ok');
      }).catch(function(e){
        if(e&&/not found/i.test(e.message||'')){
          removeFromLocalIndex(id,'Article file was already missing, so the stale Knowledge Center entry was removed.','ok');
          return;
        }
        setStatus((e&&e.message?e.message:'Article removal failed.')+' The article was not removed from the index.','err');
      });
    }
    removeFromLocalIndex(id,'Article removed from the local Knowledge Center index. Start the server to move saved article files into Articles/Bin.','ok');
  }
  function toggleMenu(){
    var menu=$('toolsMenu');
    var main=$('appMain');
    var button=$('menuToggleBtn');
    var retracted=menu.classList.toggle('retracted');
    main.classList.toggle('menu-retracted',retracted);
    button.setAttribute('aria-expanded',String(!retracted));
    button.textContent=retracted?'Tools':'Hide';
    button.title=retracted?'Open menu':'Retract menu';
  }

  document.querySelectorAll('button').forEach(function(btn){if(!btn.hasAttribute('type'))btn.setAttribute('type','button')});
  $('knowledgeTab').addEventListener('click',setCenterView);
  $('creationTab').addEventListener('click',setBuilderView);
  $('menuToggleBtn').addEventListener('click',toggleMenu);
  $('newArticleBtn').addEventListener('click',function(){resetArticleForm();setBuilderView();setStatus('New article ready.','ok')});
  $('saveArticleBtn').addEventListener('click',saveCurrentArticle);
  $('searchBtn').addEventListener('click',renderKnowledgeResults);
  $('clearSearchBtn').addEventListener('click',function(){$('knowledgeSearch').value='';renderKnowledgeResults()});
  $('knowledgeSearch').addEventListener('input',renderKnowledgeResults);
  $('knowledgeResults').addEventListener('click',function(e){var btn=e.target.closest('button');if(!btn)return;var id=btn.getAttribute('data-id'),action=btn.getAttribute('data-kb-action');if(action==='open')openIndexedArticle(id);if(action==='edit')editIndexedArticle(id);if(action==='remove')removeIndexedArticle(id)});
  $('clearBtn').addEventListener('click',function(){resetArticleForm();setStatus('Form cleared. New draft started.','ok')});
  $('importBtn').addEventListener('click',function(){$('importFile').click()});
  $('importFile').addEventListener('change',function(){var file=$('importFile').files&&$('importFile').files[0];if(!file)return;readText(file).then(function(text){loadArticleData(parseArticleContent(text,file.name),{fileName:file.name})}).catch(function(e){setStatus(e.message,'err')}).finally(function(){$('importFile').value=''})});
  window.addEventListener('beforeunload',function(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(getArticleData()))}catch(e){}});
  loadKnowledgeIndex();renderAttachmentBoxes();renderKnowledgeResults();setBuilderView();setStatus('Ready. Version: '+APP_VERSION,'ok');
})();
