import streamlit as st
import streamlit.components.v1 as components
import json, io, os, tempfile, subprocess, zipfile, shutil, re, math, datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title='PONTE AI Video Studio', page_icon='🎬', layout='centered')
st.markdown('''<style>.block-container{padding-top:1rem;max-width:850px}div.stButton>button{border-radius:12px}h1{font-size:1.8rem!important}</style>''',unsafe_allow_html=True)
st.title('🎬 PONTE AI Video Studio')
st.caption('iPhone対応 | Google Flow 半自動動画制作 | v1.3・コピー／日本語／流れるテロップ')
GENRES=['整骨院・整体','鍼灸','症状別の健康情報','ぽんトレ・パーソナルトレーニング','ぽんてアロマサロン','訪問鍼灸・マッサージ']
GENRE_ACTION={GENRES[0]:'施術前の相談と姿勢・動作の確認',GENRES[1]:'鍼灸師による丁寧な説明と落ち着いた施術環境',GENRES[2]:'日常生活での困りごとと安全なセルフケア',GENRES[3]:'トレーナーの見守りによる無理のない運動',GENRES[4]:'心地よいアロマトリートメントと落ち着いたサロン',GENRES[5]:'利用者宅での相談と穏やかな機能訓練'}
SCENES=[('共感','悩みを抱える人物の日常シーン'),('困りごと','日常生活で困る具体的な動作'),('背景','悩みに関係する生活習慣を表すシーン'),('対策','無理のない安全な対策・動作'),('サービス','専門スタッフが相談やサポートを行う様子'),('予約案内','安心した表情の人物と清潔な施設の風景')]
if 'prompts' not in st.session_state: st.session_state.prompts={}
if 'output' not in st.session_state: st.session_state.output=None
if 'render_key' not in st.session_state: st.session_state.render_key=None
if 'production_log' not in st.session_state: st.session_state.production_log={}
if 'plan_start' not in st.session_state: st.session_state.plan_start=datetime.date.today()

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

def make_video(files, captions, duration, music, title, ticker=False):
    tmp=Path(tempfile.mkdtemp(prefix='ponte_'))
    parts=[]; per=duration/len(files)
    try:
        for i,upload in enumerate(files):
            suffix=Path(upload.name).suffix.lower() or '.mp4'
            src=tmp/f'src_{i}{suffix}';src.write_bytes(upload.getvalue())
            actual=probe_duration(src)
            if actual < 0.2: raise ValueError(f'{i+1}番の動画が読み込めません')
            overlay=tmp/f'caption_{i}.png';caption_png(captions[i],overlay)
            dst=tmp/f'part_{i}.mp4'
            vf='scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=24,format=yuv420p'
            # Freeze final frame if source is shorter than requested duration
            vf+=f',tpad=stop_mode=clone:stop_duration={max(0,per-actual)+0.3:.3f}'
            overlay_expr='0:0'
            # Ticker mode: caption slides up into view during the opening second.
            if ticker: overlay_expr='0:H-min(t*180\,h)'
            run(['ffmpeg','-y','-loglevel','error','-i',str(src),'-loop','1','-i',str(overlay),'-filter_complex',f'[0:v]{vf}[base];[base][1:v]overlay={overlay_expr}:shortest=0[out]','-map','[out]','-t',str(per),'-an','-c:v','libx264','-preset','ultrafast','-crf','29','-pix_fmt','yuv420p','-movflags','+faststart',str(dst)])
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

tabs=st.tabs(['① 企画','② 日別制作計画','③ Flowプロンプト','④ 素材・編集','⑤ 完成・保存'])
with tabs[0]:
    genre=st.selectbox('ジャンル',GENRES)
    topic=st.text_input('テーマ','肩こり')
    audience=st.text_input('対象者','30〜50代の女性')
    seconds=st.selectbox('完成動画の長さ（秒）',[30,45,60],index=1)
    style=st.selectbox('映像の雰囲気',['リアルな実写広告風','温かみのある自然な映像','上品で落ち着いた広告風','親しみやすいイラスト風'])
    character=st.text_input('共通人物設定','40代の日本人女性、自然な表情、清潔感のある服装')
    language=st.selectbox('動画内の言語',['日本語（推奨）','映像は無音・字幕のみ日本語','英語'],index=0)
    location=st.text_input('背景・店舗設定','明るく清潔で親しみやすい日本の施設')
    st.session_state.config=dict(genre=genre,topic=topic,audience=audience,seconds=seconds,style=style,character=character,location=location,language=language)
    st.info('台本はテンプレートから自動作成します。外部AI APIは不要です。各シーンは次のタブで自由に編集できます。')
    if st.button('6シーンの構成を作成',type='primary',use_container_width=True):
        st.session_state.prompts={}
        for i,(name,scene) in enumerate(SCENES):
            action=GENRE_ACTION[genre]
            prompt=(f'縦型9:16、8秒、{style}。{location}。共通人物：{character}。テーマ：{topic}。対象：{audience}。'
                    f'シーン{i+1}「{name}」：{scene}。ジャンルに合う描写：{action}。'
                    '実写に近い自然な動き、自然な手指・関節・顔、安定した人物の外見、柔らかい照明。'
                    'カメラはゆっくり滑らかに移動。画面内に文字・ロゴ・字幕は生成しない。'
                    + ('音声が生成される場合は日本語で自然に話す。英語の会話は禁止。' if language=='日本語（推奨）' else '会話・ナレーションなし。' if language.startswith('映像は') else '会話がある場合は英語で話す。')
                    + '医療効果の保証や不正確な施術手技は描かない。')
            caption=[f'{topic}でお悩みではありませんか？','毎日の生活で気になることは？','身体の状態や生活習慣を見直しましょう','無理のないケアを心がけましょう',f'{genre}でお身体のご相談を','ぽんてへお気軽にご相談ください'][i]
            st.session_state.prompts[i]={'name':name,'prompt':prompt,'caption':caption}
        st.session_state.production_log={}
        st.success('構成を作成しました。②の日別制作計画で50クレジット以内に割り振り、③でプロンプトを確認してください。')
with tabs[1]:
    st.subheader('📅 1日50クレジット以内の制作計画')
    st.info('この画面は手動管理です。Google Flowの残高・生成履歴とは自動同期しません。クレジット単価や無料枠は変更されることがあるため、Flow画面の表示を優先してください。')
    c1,c2=st.columns(2)
    with c1:
        daily_limit=st.number_input('1日の利用可能クレジット',min_value=1,max_value=10000,value=50,step=10)
        cost_per_clip=st.number_input('8秒動画1本の消費クレジット',min_value=1,max_value=10000,value=10,step=1)
    with c2:
        start_date=st.date_input('制作開始日',value=st.session_state.plan_start)
        other_daily=st.number_input('他の制作で使うクレジット／日',min_value=0,max_value=10000,value=0,step=5)
    st.session_state.plan_start=start_date
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
        st.download_button('📥 日別制作計画・進捗をJSON保存',json.dumps(plan_export,ensure_ascii=False,indent=2).encode('utf-8'),file_name='ponte_daily_plan.json',mime='application/json',use_container_width=True)
        st.download_button('📥 日別制作計画をCSV保存',('日付,シーン,内容,クレジット,完了\n'+''.join(f'{row["date"]},{row["scene"]},{row["name"]},{row["credits"]},{int(st.session_state.get(f"progress_{row["scene"]-1}",False))}\n' for row in plan)).encode('utf-8-sig'),file_name='ponte_daily_plan.csv',mime='text/csv',use_container_width=True)
    st.markdown('**月4本の目安**：6シーン×4本＝24クリップ。単価10crなら240crです。無料日次枠だけを使う場合は、1動画につき2日以上に分けて作成します。')
with tabs[2]:
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
        st.download_button('📄 全プロンプトをJSONで保存',json.dumps(payload,ensure_ascii=False,indent=2).encode(),file_name='ponte_prompts.json',mime='application/json',use_container_width=True)
with tabs[3]:
    st.caption('Flowから保存したMP4をシーン順にアップロードします。個別に再生して確認できます。')
    uploads=[]
    for i in range(6):
        st.markdown(f'**シーン{i+1}：{SCENES[i][0]}**')
        upload=st.file_uploader(f'動画 {i+1}',type=['mp4','mov','m4v'],key=f'video_{i}')
        uploads.append(upload)
        if upload: st.video(upload)
    ticker=st.checkbox('テロップを下から流して表示（各シーン冒頭でスライドイン）',value=True,help='字幕は日本語で各シーンの間表示されます。オフなら固定表示です。')
    st.info('字幕は③の各シーン「完成動画の字幕」で変更できます。Flow内の文字生成は使わず、MP4結合時に正確な日本語字幕を追加します。')
    music=st.file_uploader('BGM（任意・商用利用可能なMP3/WAV/M4A）',type=['mp3','wav','m4a'])
    if music: st.audio(music)
    if st.button('🎞️ 45秒動画を結合・字幕とBGMを追加',type='primary',use_container_width=True):
        if not all(uploads): st.error('6シーンすべての動画をアップロードしてください。')
        elif not st.session_state.prompts: st.error('①で構成を作成してください。')
        else:
            with st.spinner('動画を処理しています。iPhoneではしばらく時間がかかる場合があります…'):
                try:
                    captions=[st.session_state.prompts[i]['caption'] for i in range(6)]
                    result=make_video(uploads,captions,st.session_state.get('config',{}).get('seconds',45),music,topic,ticker=ticker)
                    st.session_state.output=result
                    st.success('MP4を生成しました。⑤のタブで確認してください。')
                except Exception as e: st.error('動画処理に失敗しました。入力形式・容量を確認してください。');st.code(str(e))
with tabs[4]:
    if st.session_state.output:
        st.success('完成動画を確認できます。ダウンロード後もこの画面に残ります。')
        st.video(st.session_state.output)
        st.download_button('⬇️ 完成MP4をダウンロード',st.session_state.output,file_name='PONTE_AI_Video_Studio.mp4',mime='video/mp4',use_container_width=True)
    else: st.info('④で動画を結合すると、ここにプレビューとダウンロードボタンが表示されます。')
    st.markdown('---')
    st.caption('注意：無料Streamlit Cloudでは大きな動画の処理がメモリ・実行時間制限で失敗することがあります。動画は一時処理し、永続保存しません。患者様の実写素材は同意を得たものだけ使用してください。')
