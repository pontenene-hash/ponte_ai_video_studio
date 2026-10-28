import streamlit as st
import streamlit.components.v1 as components
import json, io, os, tempfile, subprocess, zipfile, shutil, re, math, datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title='PONTE AI Video Studio', page_icon='🎬', layout='centered')
st.markdown('''<style>.block-container{padding-top:1rem;max-width:850px}div.stButton>button{border-radius:12px}h1{font-size:1.8rem!important}</style>''',unsafe_allow_html=True)
st.title('🎬 PONTE AI Video Studio')
st.caption('iPhone対応 | Google Flow 半自動動画制作 | v1.9・写真登録ナビ・テロップなし対応')
GENRES=['整骨院・整体','鍼灸','症状別の健康情報','ぽんトレ・パーソナルトレーニング','ぽんてアロマサロン','訪問鍼灸・マッサージ']
GENRE_ACTION={GENRES[0]:'施術前の相談と姿勢・動作の確認',GENRES[1]:'鍼灸師による丁寧な説明と落ち着いた施術環境',GENRES[2]:'日常生活での困りごとと安全なセルフケア',GENRES[3]:'トレーナーの見守りによる無理のない運動',GENRES[4]:'心地よいアロマトリートメントと落ち着いたサロン',GENRES[5]:'利用者宅での相談と穏やかな機能訓練'}
SCENES=[('共感','悩みを抱える人物の日常シーン'),('困りごと','日常生活で困る具体的な動作'),('背景','悩みに関係する生活習慣を表すシーン'),('対策','無理のない安全な対策・動作'),('サービス','専門スタッフが相談やサポートを行う様子'),('予約案内','安心した表情の人物と清潔な施設の風景')]
if 'reference_library' not in st.session_state: st.session_state.reference_library={}
if 'selected_room' not in st.session_state: st.session_state.selected_room='指定なし'
if 'selected_staff' not in st.session_state: st.session_state.selected_staff='指定なし'
if 'prompts' not in st.session_state: st.session_state.prompts={}
if 'output' not in st.session_state: st.session_state.output=None
if 'render_key' not in st.session_state: st.session_state.render_key=None
if 'production_log' not in st.session_state: st.session_state.production_log={}
if 'plan_start' not in st.session_state: st.session_state.plan_start=datetime.date.today()
if 'assets' not in st.session_state: st.session_state.assets={}
if 'music_asset' not in st.session_state: st.session_state.music_asset=None
if 'config' not in st.session_state: st.session_state.config={}
if 'daily_settings' not in st.session_state: st.session_state.daily_settings={'daily_limit':50,'cost_per_clip':10,'other_daily':0}


def font_path():
    candidates=['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    return next((p for p in candidates if os.path.exists(p)),candidates[-1])

def caption_png(text, path, width=720, height=1280):
    im=Image.new('RGBA',(width,height),(0,0,0,0)); d=ImageDraw.Draw(im)
    f=ImageFont.truetype(font_path(),40)
    # Japanese-safe character wrapping
    lines=[]; line=''
    for char in text:
        trial=line+char
        if d.textbbox((0,0),trial,font=f)[2] > width-100 and line:
            lines.append(line);line=char
        else: line=trial
    if line:lines.append(line)
    lines=lines[:4]; lh=58; y=height-125-len(lines)*lh
    d.rounded_rectangle((30,y-20,width-30,y+len(lines)*lh+18),radius=24,fill=(8,24,35,205))
    for i,line in enumerate(lines):
        bb=d.textbbox((0,0),line,font=f); x=(width-(bb[2]-bb[0]))/2
        d.text((x,y+i*lh),line,font=f,fill='white',stroke_width=1,stroke_fill='#16202a')
    im.save(path)

def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
    if p.returncode: raise RuntimeError(p.stderr[-1400:])

def probe_duration(p):
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],capture_output=True,text=True,timeout=15)
    return float(r.stdout.strip() or '0')

def copy_widget(value, idx):
    # Clipboard action runs in the browser; textarea fallback for restrictive iOS contexts.
    literal=json.dumps(value, ensure_ascii=False).replace('</', '<\\/')
    components.html(f'''<div style="font-family:sans-serif;display:flex;gap:8px;align-items:center">
<button id="copy" style="border:0;border-radius:10px;padding:12px 18px;background:#187b69;color:white;font-weight:bold">📋 プロンプトをコピー</button>
<span id="status" style="font-size:12px;color:#555"></span></div>
<script>
const value={literal};
document.getElementById('copy').onclick=async()=>{{
 try {{ await navigator.clipboard.writeText(value);document.getElementById('status').textContent='コピーしました'; }}
 catch(e) {{ const ta=document.createElement('textarea');ta.value=value;document.body.appendChild(ta);ta.select();
 const ok=document.execCommand('copy');document.body.removeChild(ta);
 document.getElementById('status').textContent=ok?'コピーしました':'下のコード右上のコピーボタンをご利用ください'; }}
}};
</script>''',height=58)

def make_video(files, captions, duration, music, title, ticker_mode="下からスライドイン"):
    tmp=Path(tempfile.mkdtemp(prefix='ponte_'))
    parts=[]; per=duration/len(files)
    try:
        for i,upload in enumerate(files):
            suffix=Path(upload.name).suffix.lower() or '.mp4'
            src=tmp/f'src_{i}{suffix}';src.write_bytes(upload.getvalue())
            actual=probe_duration(src)
            if actual < 0.2: raise ValueError(f'{i+1}番の動画が読み込めません')
            overlay=tmp/f'caption_{i}.png'
            if ticker_mode!='テロップなし': caption_png(captions[i],overlay)
            dst=tmp/f'part_{i}.mp4'
            vf='scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=24,format=yuv420p'
            # Freeze final frame if source is shorter than requested duration
            vf+=f',tpad=stop_mode=clone:stop_duration={max(0,per-actual)+0.3:.3f}'
            overlay_expr='0:0'
            overlay_filter='[1:v]format=rgba[cap];'
            if ticker_mode=='下からスライドイン':
                overlay_expr='0:max(0\,H-min(t*1200\,H))'
            elif ticker_mode=='右からスライドイン':
                overlay_expr='max(0\,W-min(t*850\,W)):0'
            elif ticker_mode=='フェードイン':
                overlay_filter='[1:v]format=rgba,fade=t=in:st=0:d=1:alpha=1[cap];'
            if ticker_mode=='テロップなし':
                cmd=['ffmpeg','-y','-loglevel','error','-i',str(src),'-vf',vf,'-t',str(per),'-an','-c:v','libx264','-preset','ultrafast','-crf','29','-pix_fmt','yuv420p','-movflags','+faststart',str(dst)]
            else:
                cmd=['ffmpeg','-y','-loglevel','error','-i',str(src),'-loop','1','-i',str(overlay),'-filter_complex',f'[0:v]{vf}[base];{overlay_filter}[base][cap]overlay={overlay_expr}:shortest=0[out]','-map','[out]','-t',str(per),'-an','-c:v','libx264','-preset','ultrafast','-crf','29','-pix_fmt','yuv420p','-movflags','+faststart',str(dst)]
            run(cmd)
            parts.append(dst)
        listing=tmp/'concat.txt';listing.write_text(''.join(f"file '{p}'\n" for p in parts))
        silent=tmp/'silent.mp4'
        run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(silent)])
        final=tmp/'final.mp4'
        if music:
            audio=tmp/('bgm'+(Path(music.name).suffix.lower() or '.mp3'));audio.write_bytes(music.getvalue())
            run(['ffmpeg','-y','-loglevel','error','-i',str(silent),'-stream_loop','-1','-i',str(audio),'-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','copy','-c:a','aac','-b:a','128k','-af','volume=0.22,afade=t=in:st=0:d=1,afade=t=out:st='+str(max(0,duration-2))+':d=2','-movflags','+faststart',str(final)])
        else: shutil.copy(silent,final)
        return final.read_bytes()
    finally: shutil.rmtree(tmp,ignore_errors=True)


class SavedUpload:
    def __init__(self,name,data): self.name=name;self._data=data
    def getvalue(self): return self._data

def project_manifest():
    return {'version':2,'config':st.session_state.get('config',{}),
            'prompts':{str(k):v for k,v in st.session_state.prompts.items()},
            'production_log':st.session_state.get('production_log',{}),
            'progress':[bool(st.session_state.get(f'progress_{i}',False)) for i in range(6)],
            'plan_start':st.session_state.plan_start.isoformat(),
            'daily_settings':st.session_state.get('daily_settings',{}),
            'assets':{str(k):v['name'] for k,v in st.session_state.assets.items()},
            'music':st.session_state.music_asset['name'] if st.session_state.music_asset else None,
            'has_output':bool(st.session_state.output),
            'references':{k:{'kind':v['kind'],'name':v['name'],'note':v.get('note',''),'filename':v['filename']} for k,v in st.session_state.reference_library.items()},
            'selected_room':st.session_state.selected_room,'selected_staff':st.session_state.selected_staff}

def project_zip(include_media=True):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        z.writestr('project.json',json.dumps(project_manifest(),ensure_ascii=False,indent=2))
        if include_media:
            for key,ref in st.session_state.reference_library.items():
                z.writestr('references/'+key+Path(ref['filename']).suffix.lower(),ref['bytes'])
            for k,v in st.session_state.assets.items():
                z.writestr(f'media/scene_{k}{Path(v["name"]).suffix.lower() or ".mp4"}',v['bytes'])
            if st.session_state.music_asset:
                v=st.session_state.music_asset
                z.writestr('media/music'+(Path(v['name']).suffix.lower() or '.mp3'),v['bytes'])
            if st.session_state.output:
                z.writestr('output/completed.mp4',st.session_state.output)
    return buffer.getvalue()

def restore_project(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names=z.namelist()
        if len(names)>30 or sum(x.file_size for x in z.infolist())>650*1024*1024:
            raise ValueError('バックアップの容量またはファイル数が上限を超えています')
        if 'project.json' not in names: raise ValueError('project.jsonが含まれていません')
        data=json.loads(z.read('project.json'))
        if not isinstance(data,dict) or 'prompts' not in data: raise ValueError('プロジェクト形式が正しくありません')
        cfg=data.get('config',{})
        st.session_state.config=cfg
        for key in ('genre','topic','audience','seconds','style','character','language','location'):
            if key in cfg: st.session_state['setting_'+key]=cfg[key]
        st.session_state.prompts={int(k):v for k,v in data['prompts'].items() if str(k).isdigit() and 0<=int(k)<6}
        for i,v in st.session_state.prompts.items():
            st.session_state[f'prompt_{i}']=v.get('prompt','')
            st.session_state[f'caption_{i}']=v.get('caption','')
        for i,v in enumerate(data.get('progress',[])[:6]):st.session_state[f'progress_{i}']=bool(v)
        st.session_state.plan_start=datetime.date.fromisoformat(data.get('plan_start',datetime.date.today().isoformat()))
        st.session_state.daily_settings=data.get('daily_settings',{})
        st.session_state.production_log=data.get('production_log',{})
        st.session_state.reference_library={}
        for key,ref in data.get('references',{}).items():
            matches=[n for n in names if n.startswith('references/'+key+'.')]
            if matches:
                st.session_state.reference_library[key]={**ref,'bytes':z.read(matches[0])}
        st.session_state.selected_room=data.get('selected_room','指定なし')
        st.session_state.selected_staff=data.get('selected_staff','指定なし')
        st.session_state.assets={}
        for i in range(6): st.session_state.pop(f'video_{i}',None)
        for i in range(6):
            paths=[n for n in names if n.startswith(f'media/scene_{i}.')]
            if paths:
                name=data.get('assets',{}).get(str(i),Path(paths[0]).name)
                st.session_state.assets[i]={'name':name,'bytes':z.read(paths[0])}
        tracks=[n for n in names if n.startswith('media/music.')]
        st.session_state.music_asset={'name':data.get('music') or 'music.mp3','bytes':z.read(tracks[0])} if tracks else None
        st.session_state.output=z.read('output/completed.mp4') if 'output/completed.mp4' in names else None

def restore_json(blob):
    data=json.loads(blob)
    if 'scenes' in data: data={'prompts':data['scenes'],'config':data.get('config',{})}
    if 'plan' in data and 'prompts' not in data:
        for row in data['plan']:
            i=int(row.get('scene',0))-1
            if 0<=i<6: st.session_state[f'progress_{i}']=bool(row.get('done',False))
        st.session_state.daily_settings={k:data[k] for k in ('daily_limit','other_daily','cost_per_clip') if k in data}
        return '日別計画・進捗を復元しました（台本は含まれていません）。'
    if 'prompts' not in data: raise ValueError('対応するJSONではありません')
    st.session_state.config=data.get('config',{})
    for key,val in st.session_state.config.items():
        if key in ('genre','topic','audience','seconds','style','character','language','location'):st.session_state['setting_'+key]=val
    st.session_state.prompts={int(k):v for k,v in data['prompts'].items() if str(k).isdigit() and 0<=int(k)<6}
    for i,v in st.session_state.prompts.items():
        st.session_state[f'prompt_{i}']=v.get('prompt','')
        st.session_state[f'caption_{i}']=v.get('caption','')
    return '台本・プロンプトを復元しました。動画素材は必要に応じて再アップロードしてください。'

PAGES=['① 企画','② 日別制作計画','③ Flowプロンプト','④ 素材・編集','⑤ 完成・保存','⑦ 店舗・人物登録']
st.info('📱 ファイルのプレビュー画面へ移動しないよう、計画・プロンプトはアプリ内で表示・コピーできます。動画・ZIPの保存時のみiPhoneの保存画面が開く場合があります。')
page=st.segmented_control('📍 画面を切り替える',PAGES+['⑥ 保存・再開'],default=PAGES[0],key='active_page',selection_mode='single') or PAGES[0]
st.caption('画面を切り替えても作業は保持されます。ただしStreamlitの再起動・接続切断に備えてZIPバックアップを保存してください。')
if page == '⑥ 保存・再開':
    st.subheader('💾 作業の保存・再開')
    st.write('**画面を移動せずに保存したい場合**は、下の「保存用テキスト」をコピーしてiPhoneのメモに貼り付けてください。翌日はそのテキストを貼り付けると台本・進捗を復元できます。動画素材を含む場合はZIPバックアップを使用します。')
    st.markdown('#### 📋 アプリ内で保存（ダウンロード不要）')
    project_text=json.dumps(project_manifest(),ensure_ascii=False,indent=2)
    st.code(project_text,language='json')
    copy_widget(project_text,99)
    st.caption('コピーした内容をiPhoneの「メモ」に貼り付けて保管してください。動画・BGMの実ファイルは含みません。')
    resume_text=st.text_area('🔄 前回の保存用テキストを貼り付け',height=110,key='resume_text',placeholder='前回コピーしたJSONテキストをここに貼り付け')
    if st.button('貼り付けたテキストから再開',use_container_width=True,disabled=not resume_text.strip()):
        try:
            data=json.loads(resume_text)
            if 'version' in data and 'progress' in data and 'prompts' in data:
                restore_json(json.dumps(data,ensure_ascii=False).encode('utf-8'))
                for i,done in enumerate(data.get('progress',[])[:6]): st.session_state[f'progress_{i}']=bool(done)
                st.session_state.daily_settings=data.get('daily_settings',st.session_state.daily_settings)
                st.session_state.plan_start=datetime.date.fromisoformat(data.get('plan_start',datetime.date.today().isoformat()))
            else: restore_json(resume_text.encode('utf-8'))
            st.success('台本と進捗を復元しました。上のタブで制作を再開できます。')
        except Exception as e: st.error(f'復元できませんでした：{e}')
    st.divider()
    st.markdown('#### 📦 動画・店舗写真・スタッフ写真も含めて保存（推奨）')
    include_media=st.checkbox('動画素材・BGM・完成MP4もバックアップに含める',value=True)
    st.warning('登録写真を次回に引き継ぐには、素材入りZIPを選んでください。動画を含むZIPは大きくなります。iPhoneで容量不足の場合はチェックを外して台本と進捗のみ保存してください。')
    if st.button('📦 バックアップファイルを準備',use_container_width=True):
        try:
            st.session_state.backup_blob=project_zip(include_media)
            st.success('準備できました。下のZIPを保存してください。')
        except Exception as e: st.error(f'バックアップの準備に失敗しました：{e}')
    if st.session_state.get('backup_blob'):
        st.download_button('⬇️ 作業バックアップ（ZIP）を保存',st.session_state.backup_blob,
                           file_name='PONTE_project_'+datetime.date.today().strftime('%Y%m%d')+'.zip',
                           mime='application/zip',on_click='ignore',use_container_width=True)
    st.divider()
    st.markdown('**以前の作業を再開する**')
    restore_file=st.file_uploader('以前保存したZIPまたは旧版JSONを選択',type=['zip','json'],key='restore_file')
    if restore_file and st.button('🔄 このファイルから作業を復元',type='primary',use_container_width=True):
        try:
            if restore_file.name.lower().endswith('.zip'):
                restore_project(restore_file.getvalue())
                message='台本・進捗・保存済み動画を復元しました。'
            else: message=restore_json(restore_file.getvalue())
            st.session_state.backup_blob=None
            st.session_state.restore_notice=message
            st.rerun()
        except Exception as e: st.error(f'復元できませんでした：{e}')
    if st.session_state.get('restore_notice'):
        st.success(st.session_state.pop('restore_notice'))
    st.info('旧版の ponte_prompts.json は台本のみ、ponte_daily_plan.json は進捗のみ復元できます。両方を完全統合するには、それぞれ順に読み込んでください。')
    st.markdown('**iPhoneでファイル画面から戻るには**：Safariに戻り、タブ一覧からStreamlitの画面を選びます。ChatGPT内ブラウザの場合はSafariでアプリURLを開き直す方が安定します。')
if page == '⑦ 店舗・人物登録':
    st.subheader('🏠 店舗写真・実在スタッフを登録')
    st.info('写真は現在のセッション内に保存されます。次回も使うには⑥「保存・再開」で「動画素材・BGMも含める」にチェックを入れてZIP保存してください。写真はGoogle Flowに自動送信されません。')
    kind=st.radio('登録する種類',['店舗・部屋','スタッフ・インストラクター'],horizontal=True)
    ref_name=st.text_input('登録名（例：ぽんトレ・トレーニング室 / 山田トレーナー）',key='ref_name')
    ref_note=st.text_input('特徴・服装・背景などのメモ',key='ref_note')
    ref_file=st.file_uploader('写真を選択（JPG・PNG・WEBP）',type=['jpg','jpeg','png','webp'],key='reference_upload')
    if ref_file: st.image(ref_file,caption='登録する参考画像',use_container_width=True)
    if st.button('📸 この写真を登録',type='primary',disabled=not(ref_name.strip() and ref_file),use_container_width=True):
        import uuid
        key=uuid.uuid4().hex[:12]
        st.session_state.reference_library[key]={'kind':kind,'name':ref_name.strip(),'note':ref_note.strip(),'filename':ref_file.name,'bytes':ref_file.getvalue()}
        st.success('登録しました。①企画に戻り、参考写真の選択欄から選んでください。⑥で素材入りZIPを保存すると次回も利用できます。')
        if st.button('① 企画へ戻って写真を選ぶ',key='go_plan_after_ref'):
            st.session_state.active_page='① 企画'
            st.rerun()
    st.markdown('#### 登録済みの参考画像')
    if not st.session_state.reference_library: st.caption('まだ写真が登録されていません。')
    for key,ref in list(st.session_state.reference_library.items()):
        with st.expander(f"{'🏠' if ref['kind']=='店舗・部屋' else '👤'} {ref['name']}"):
            st.image(ref['bytes'],width=280)
            st.caption(ref.get('note',''))
            st.download_button('⬇️ Google Flowにアップロードする写真を保存',ref['bytes'],file_name=ref['filename'],mime='image/jpeg' if ref['filename'].lower().endswith(('.jpg','.jpeg')) else 'image/png',key='download_ref_'+key,on_click='ignore')
            if st.button('登録を削除',key='delete_ref_'+key):
                del st.session_state.reference_library[key]
                st.rerun()
    if st.button('⬅ ① 企画に戻る',key='return_to_plan',use_container_width=True):
        st.session_state.active_page='① 企画'
        st.rerun()
    st.warning('実在スタッフの写真・動画は本人の同意を得て使用してください。Flow側の人物画像利用制限や再現精度によっては生成できない場合があります。')

if page == PAGES[0]:
    for k,v in st.session_state.get('config',{}).items():
        if k in ('genre','topic','audience','seconds','style','character','language','location') and 'setting_'+k not in st.session_state:
            st.session_state['setting_'+k]=v
    genre=st.selectbox('ジャンル',GENRES,key='setting_genre')
    topic=st.text_input('テーマ','肩こり',key='setting_topic')
    audience=st.text_input('対象者','30〜50代の女性',key='setting_audience')
    seconds=st.selectbox('完成動画の長さ（秒）',[30,45,60],index=1,key='setting_seconds')
    style=st.selectbox('映像の雰囲気',['リアルな実写広告風','温かみのある自然な映像','上品で落ち着いた広告風','親しみやすいイラスト風'],key='setting_style')
    character=st.text_input('共通人物設定','40代の日本人女性、自然な表情、清潔感のある服装',key='setting_character')
    language=st.selectbox('動画内の言語',['日本語（推奨）','映像は無音・字幕のみ日本語','英語'],index=0,key='setting_language')
    location=st.text_input('背景・店舗設定','明るく清潔で親しみやすい日本の施設',key='setting_location')
    st.session_state.config=dict(genre=genre,topic=topic,audience=audience,seconds=seconds,style=style,character=character,location=location,language=language)
    rooms=['指定なし']+[k for k,v in st.session_state.reference_library.items() if v['kind']=='店舗・部屋']
    staff=['指定なし']+[k for k,v in st.session_state.reference_library.items() if v['kind']=='スタッフ・インストラクター']
    st.selectbox('参考にする実際の店舗写真',rooms,format_func=lambda k:st.session_state.reference_library[k]['name'] if k!='指定なし' else '指定なし',key='selected_room')
    st.selectbox('参考にする実在スタッフ写真',staff,format_func=lambda k:st.session_state.reference_library[k]['name'] if k!='指定なし' else '指定なし',key='selected_staff')
    if len(rooms)==1 or len(staff)==1:
        missing=[]
        if len(rooms)==1: missing.append('店舗写真')
        if len(staff)==1: missing.append('スタッフ写真')
        st.warning('・'.join(missing)+'が未登録です。「⑦ 店舗・人物登録」で写真を追加すると、この選択欄に表示されます。')
        if st.button('📸 写真登録画面へ移動',use_container_width=True):
            st.session_state.active_page='⑦ 店舗・人物登録'
            st.rerun()
    else:
        st.success('登録済みの店舗・スタッフ写真を選べます。')
    if st.session_state.selected_room!='指定なし' and st.session_state.selected_room in st.session_state.reference_library:
        st.image(st.session_state.reference_library[st.session_state.selected_room]['bytes'],caption='選択中の店舗写真',width=260)
    if st.session_state.selected_staff!='指定なし' and st.session_state.selected_staff in st.session_state.reference_library:
        st.image(st.session_state.reference_library[st.session_state.selected_staff]['bytes'],caption='選択中のスタッフ写真',width=260)
    st.info('台本はテンプレートから自動作成します。外部AI APIは不要です。各シーンは次のタブで自由に編集できます。')
    if st.button('6シーンの構成を作成',type='primary',use_container_width=True):
        st.session_state.prompts={}
        for i,(name,scene) in enumerate(SCENES):
            action=GENRE_ACTION[genre]
            refs=[]
            for key,label in [(st.session_state.selected_room,'背景'),(st.session_state.selected_staff,'人物')]:
                if key!='指定なし' and key in st.session_state.reference_library:
                    ref=st.session_state.reference_library[key]
                    refs.append(f'{label}参考画像「{ref["name"]}」をGoogle Flowに手動でアップロードして参照。{ref.get("note","")}。')
            ref_instruction=' '.join(refs)+' 参考画像の人物・内装の一貫性をできるだけ保つ（完全一致は保証されない）。' if refs else ''
            prompt=(ref_instruction+f'縦型9:16、8秒、{style}。{location}。共通人物：{character}。テーマ：{topic}。対象：{audience}。'
                    f'シーン{i+1}「{name}」：{scene}。ジャンルに合う描写：{action}。'
                    '実写に近い自然な動き、自然な手指・関節・顔、安定した人物の外見、柔らかい照明。'
                    'カメラはゆっくり滑らかに移動。画面内に文字・ロゴ・字幕は生成しない。'
                    + ('音声が生成される場合は日本語で自然に話す。英語の会話は禁止。' if language=='日本語（推奨）' else '会話・ナレーションなし。' if language.startswith('映像は') else '会話がある場合は英語で話す。')
                    + '医療効果の保証や不正確な施術手技は描かない。')
            caption=[f'{topic}でお悩みではありませんか？','毎日の生活で気になることは？','身体の状態や生活習慣を見直しましょう','無理のないケアを心がけましょう',f'{genre}でお身体のご相談を','ぽんてへお気軽にご相談ください'][i]
            st.session_state.prompts[i]={'name':name,'prompt':prompt,'caption':caption}
        st.session_state.production_log={}
        st.success('構成を作成しました。②の日別制作計画で50クレジット以内に割り振り、③でプロンプトを確認してください。')
if page == PAGES[1]:
    st.subheader('📅 1日50クレジット以内の制作計画')
    st.info('この画面は手動管理です。Google Flowの残高・生成履歴とは自動同期しません。クレジット単価や無料枠は変更されることがあるため、Flow画面の表示を優先してください。')
    c1,c2=st.columns(2)
    with c1:
        daily_limit=st.number_input('1日の利用可能クレジット',min_value=1,max_value=10000,value=int(st.session_state.daily_settings.get('daily_limit',50)),step=10)
        cost_per_clip=st.number_input('8秒動画1本の消費クレジット',min_value=1,max_value=10000,value=int(st.session_state.daily_settings.get('cost_per_clip',10)),step=1)
    with c2:
        start_date=st.date_input('制作開始日',value=st.session_state.plan_start)
        other_daily=st.number_input('他の制作で使うクレジット／日',min_value=0,max_value=10000,value=int(st.session_state.daily_settings.get('other_daily',0)),step=5)
    st.session_state.plan_start=start_date
    st.session_state.daily_settings={'daily_limit':int(daily_limit),'cost_per_clip':int(cost_per_clip),'other_daily':int(other_daily)}
    usable=max(0,int(daily_limit)-int(other_daily))
    max_scenes_per_day=3
    clips_per_day=min(max_scenes_per_day,usable//int(cost_per_clip))
    st.metric('1日に計画する8秒クリップ',f'{clips_per_day}本（上限3本）')
    if not st.session_state.prompts:
        st.warning('先に①で6シーンの構成を作成してください。')
    elif clips_per_day<1:
        st.error('現在の設定では1本も生成できません。1日の残高・単価を確認してください。')
    else:
        count=len(st.session_state.prompts)
        days=math.ceil(count/clips_per_day)
        st.success(f'{count}シーンを{days}日間に分割。各日最大{clips_per_day}本・{clips_per_day*cost_per_clip}クレジットです。標準設定では1日目3シーン、2日目3シーンです。')
        plan=[]
        for i in range(count):
            date=start_date+datetime.timedelta(days=i//clips_per_day)
            key=str(i)
            plan.append({'scene':i+1,'name':st.session_state.prompts[i]['name'],'date':date.isoformat(),'credits':int(cost_per_clip)})
        for date in dict.fromkeys(row['date'] for row in plan):
            day_rows=[row for row in plan if row['date']==date]
            st.markdown(f'**{date} — {len(day_rows)}本／{sum(x["credits"] for x in day_rows)}クレジット**')
            for row in day_rows:
                idx=row['scene']-1
                st.checkbox(f'シーン{row["scene"]}：{row["name"]}　（{row["credits"]}cr）',key=f'progress_{idx}',help='Flowで生成・保存できたらチェックしてください')
        st.caption('各日最大3シーンに制限し、残りのクレジットを再生成用に確保します。再生成もクレジットを消費します。再生成時は「他の制作で使うクレジット／日」に追加消費を反映するか、開始日を調整してください。50クレジットは1日の予算上限であり、利用可能残高を保証しません。')
        plan_export={'daily_limit':int(daily_limit),'other_daily':int(other_daily),'cost_per_clip':int(cost_per_clip),'plan':[{**row,'done':bool(st.session_state.get(f'progress_{row["scene"]-1}',False))} for row in plan]}
        st.markdown('**📋 日別計画・進捗をアプリ内でコピー**')
        st.code(json.dumps(plan_export,ensure_ascii=False,indent=2),language='json')
        copy_widget(json.dumps(plan_export,ensure_ascii=False,indent=2),97)
        st.caption('JSON/CSVの直接ダウンロードボタンは、iPhoneでプレビュー画面に移動するため廃止しました。')
    st.markdown('**月4本の目安**：6シーン×4本＝24クリップ。単価10crなら240crです。無料日次枠だけを使う場合は、1動画につき2日以上に分けて作成します。')
if page == PAGES[2]:
    if not st.session_state.prompts: st.warning('①で「6シーンの構成を作成」を押してください。')
    else:
        st.markdown('[Google Flowを開く ↗](https://flow.google/)')
        st.caption('緑の「📋 プロンプトをコピー」ボタンでコピーできます。iPhoneでコピーできない場合は下のコード右上のコピーアイコンを使用してください。Flowでは音声言語が必ず指定どおりになるとは限らないため、最終版の日本語テロップはこのアプリで重ねます。')
        for i in range(6):
            data=st.session_state.prompts[i]
            with st.expander(f'シーン{i+1}：{data["name"]}',expanded=i==0):
                data['prompt']=st.text_area('Flow用プロンプト',data['prompt'],height=170,key=f'prompt_{i}')
                data['caption']=st.text_input('完成動画の字幕',data['caption'],key=f'caption_{i}')
                copy_widget(data['prompt'],i)
                st.code(data['prompt'],language=None)
        payload={'config':st.session_state.get('config',{}),'scenes':st.session_state.prompts}
        st.download_button('⬇️ FlowプロンプトをJSONでダウンロード',json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8'),file_name='ponte_prompts.json',mime='application/json',on_click='ignore',use_container_width=True)
        st.info('登録写真は⑦で個別に保存し、Google Flow側に手動でアップロードしてください。')
        st.markdown('**📋 全プロンプトをまとめてコピー**')
        st.code(json.dumps(payload,ensure_ascii=False,indent=2),language='json')
        copy_widget(json.dumps(payload,ensure_ascii=False,indent=2),98)
if page == PAGES[3]:
    st.caption('Flowから保存したMP4をシーン順にアップロードします。個別に再生して確認できます。')
    uploads=[]
    for i in range(6):
        st.markdown(f'**シーン{i+1}：{SCENES[i][0]}**')
        upload=st.file_uploader(f'動画 {i+1}',type=['mp4','mov','m4v'],key=f'video_{i}')
        if upload:
            old=st.session_state.assets.get(i)
            if old is None or old['name']!=upload.name or old['bytes']!=upload.getvalue():
                st.session_state.assets[i]={'name':upload.name,'bytes':upload.getvalue()}
        saved=st.session_state.assets.get(i)
        if saved:
            st.caption('保存済み：'+saved['name'])
            st.video(saved['bytes'])
            if st.button('このシーンの素材を削除',key=f'remove_video_{i}'):
                st.session_state.assets.pop(i,None)
                st.rerun()
            uploads.append(SavedUpload(saved['name'],saved['bytes']))
        else: uploads.append(None)
    ticker_mode=st.selectbox('🎞️ 日本語コメントのテロップ演出',['テロップなし','下からスライドイン','右からスライドイン','フェードイン','固定表示'],help='テロップなしを選ぶと字幕画像を作成せず、動画とBGMのみを結合します。その他は③の日本語コメントを焼き込みます。')
    if ticker_mode=='テロップなし':
        st.info('テロップなし：完成MP4に文字を重ねません。BGMは追加できます。')
    else:
        st.info('字幕は③の各シーン「完成動画の字幕」で変更できます。Flow内の文字生成は使わず、MP4結合時に正確な日本語字幕を追加します。')
    music=st.file_uploader('BGM（任意・商用利用可能なMP3/WAV/M4A）',type=['mp3','wav','m4a'])
    if music: st.session_state.music_asset={'name':music.name,'bytes':music.getvalue()}
    if st.session_state.music_asset:
        st.caption('BGM保存済み：'+st.session_state.music_asset['name'])
        st.audio(st.session_state.music_asset['bytes'])
        if st.button('BGMを削除'):
            st.session_state.music_asset=None
            st.rerun()
    music=SavedUpload(st.session_state.music_asset['name'],st.session_state.music_asset['bytes']) if st.session_state.music_asset else None
    if st.button('🎞️ 45秒動画を結合・字幕とBGMを追加',type='primary',use_container_width=True):
        if not all(uploads): st.error('6シーンすべての動画をアップロードしてください。')
        elif not st.session_state.prompts: st.error('①で構成を作成してください。')
        else:
            with st.spinner('動画を処理しています。iPhoneではしばらく時間がかかる場合があります…'):
                try:
                    captions=[st.session_state.prompts[i]['caption'] for i in range(6)]
                    result=make_video(uploads,captions,st.session_state.get('config',{}).get('seconds',45),music,st.session_state.get('config',{}).get('topic',''),ticker_mode=ticker_mode)
                    st.session_state.output=result
                    st.success('MP4を生成しました。⑤のタブで確認してください。')
                except Exception as e: st.error('動画処理に失敗しました。入力形式・容量を確認してください。');st.code(str(e))
if page == PAGES[4]:
    if st.session_state.output:
        st.success('完成動画を確認できます。ダウンロード後はSafariの元のタブへ戻ると作業を続けられます。')
        st.video(st.session_state.output)
        st.download_button('⬇️ 完成MP4をダウンロード',st.session_state.output,file_name='PONTE_AI_Video_Studio.mp4',mime='video/mp4',use_container_width=True,on_click='ignore')
    else: st.info('④で動画を結合すると、ここにプレビューとダウンロードボタンが表示されます。')
    st.info('中断・再開する場合は⑥ 保存・再開からZIPバックアップを作成してください。')
    st.markdown('---')
    st.caption('注意：無料Streamlit Cloudでは大きな動画の処理がメモリ・実行時間制限で失敗することがあります。動画は一時処理し、永続保存しません。患者様の実写素材は同意を得たものだけ使用してください。')
