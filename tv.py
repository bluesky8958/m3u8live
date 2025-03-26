#coding:utf-8
import requests,re,json,time,os,sqlite3,datetime
from urllib.parse import quote
from bottle import Bottle,request,response,static_file,run
app = Bottle()
response.set_header('Access-Control-Allow-Origin','*')
host='http://www.qianzai56.com:88'
head={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.87 Safari/537.36 SE 2.X MetaSr 1.0'}
cross={'Content-Type':'application/x-mpegurl,video/mp2t','Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers': '*','Access-Control-Allow-Methods': '*'}
player=r'''<!DOCTYPE html>
<html>
    <head>
        <title>player</title>
        <meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1,minimum-scale=1,user-scalable=no,minimal-ui">
        <meta name="referrer" content="no-referrer">
        <style type="text/css">html,body {{height:100%;margin:0;overflow: hidden;background-color:black;}}#mse {{height:100% !important;}}</style>
    </head>
    <body>
        <div id="mse"></div>
        <script src="http://unpkg.byted-static.com/xgplayer/2.31.6/browser/index.js" charset="utf-8"></script>
        <script src="http://unpkg.byted-static.com/xgplayer-hls.js/2.2.2/browser/index.js" charset="utf-8"></script>
        <script>
            let player = new HlsJsPlayer({{id:"mse",width:"100%",fluid: true,playsinline:true,whitelist: [""],autoplay: true,ignores: ['time','progress'],url:"{}",fitVideoSize:'auto'}}) 
        </script>
    </body>
</html>''' 
#---------------------------------------------tv live function---------------------------------
def sql(db='',tag=1): #tag 0.未建表 1.已建表
    if tag == 0:return "未建表！"
    sqlite=sqlite3.connect('./tv.db') #连接数据库
    sqlite.row_factory = sqlite3.Row
    cur=sqlite.cursor()
    if db == 'VACUUM':
        cur.execute(db)
        data = '数据库收缩完成！'
    else:
        try:
            data = cur.execute(db).fetchall()
            if len(data) > 0: data = json.dumps([dict(d) for d in data])
        except sqlite3.Error as e:
            data = ''
    sqlite.commit()
    sqlite.close()
    return data

def theading(func,vals,work=20):
    runok = []
    if len(vals)==0:return runok
    import concurrent.futures as futures
    with futures.ThreadPoolExecutor(max_workers=work) as exe:
        threads = {exe.submit(func, url): url for url in vals}
        for thead in futures.as_completed(threads):
            url = threads[thead]
            result = (thead.result(),vals.index(url))
            if result and result[0] != 404:runok.append(result)
    runok.sort(key=lambda x: x[1])  # 根据初始顺序排序
    return runok

def check(txt,fp='0'):   
    def check_url(url): 
        if url.find('#genre#') != -1:return url
        try:
            res = requests.head(url.split(',')[1].strip(),headers=head,timeout=7)
            if res.status_code == 200: return url
        except:
            return 404
    if fp == '0':
        lines = txt.split('\n')
    else:
        with open(txt, "r",encoding="utf8") as file:
            lines = file.readlines()
    runok = theading(check_url,lines,20)
    lines = [url[0] for url in runok]
    if fp == '1':
        with open(txt, "w",encoding="utf8") as file:
            file.writelines(lines+'\n')
    return lines

def tss(uts,types='no||'): #ts切片序列简化和还原
    t0,t1,t2 = types.split("|")
    if t0=='no':
        ts,ext = uts.split(".")
        if ts.isalnum() and ts[-1]=='0':
            if ts[-3:-1]=='00':
                return 'sn|{}|{}'.format(ts[:-3],ext) #定长字母数字组合
            return 'an|{}|{}'.format(ts[:-1],ext) #字母数字组合
        elif ts.isdigit():
            if len(ts)==1:
                return 'nn|0|{}'.format(ext) #数字序列
            return 'mn|{}|{}'.format(len(ts),ext) #定长数字组合
        else:
            return 'aa|all|{}'.format(ext) #随机序列组合
    elif t0=='nn':
        return '{}.{}'.format(uts,t2)
    elif t0=='mn':
        return "{:0>{}}.{}".format(uts,t1,t2)
    elif t0=='sn':
        return t1+"{:0>{}}.{}".format(uts,3,t2)
    elif t0=='an':
        return '{}{}.{}'.format(t1,uts,t2)
    elif t0=='aa':
        ts=json.loads(t1)
        return '{}.{}'.format(ts[uts],t2)

def tsu(res,rec,url="",doc=""): #ts切片url补全
    if doc.find(res) != -1:
        u = re.compile(rec).findall(doc)[0]
        if u.find('http') != -1:
            url = u
        elif u[0]=='/':
            url = re.compile('.*//.*?/').findall(url)[0][:-1] + u
        else:
            url = re.compile('.*/').findall(url)[0] + u
    return url

def tsp(data,pag):
    def li(x):
        x = json.loads(data[x])
        d = x[0] if len(x)==1 else x[pag]
        return d
    tt,uri,ts,host = li('tt'),li('uri'),li('ts'),li('host')
    aes = json.loads(data['aes'])
    k = aes[0][0] if len(aes[0])==1 else aes[0][pag]
    aes = '\n' if k=='no' else k.format(aes[1][0]) if len(aes[1])==1 and aes[1][0]!='' else k.format(aes[1][pag])
    return [host+uri,ts,aes,tt]

def m3u8(u):
    data={}
    u = quote(u).replace('%3A//','://') #链接中文编码
    try:
        doc = requests.get(u,headers=head,timeout=10).text
        u2 = tsu('#EXT-X-STREAM-INF','\s(.*m3u8)',u,doc) #判断二级列表
        if u2 != u:doc = requests.get(u2,headers=head,timeout=6).text
    except:
        return 404
    tt = re.compile(r'#EXTINF:(.*?),\s+(.*?)(\w+\.\w+)\s',re.M).findall(doc)#获取ts
    if len(tt) == 0:return 404
    kk = re.compile('#EXT-X-KEY.*URI=".*\S').findall(doc) #判断是否加密
    if len(kk) == 0:
        data['aes'] = ['no','']
    else:
        k = tsu('#EXT-X-KEY','"(.*\.key)"',u2,kk[0]) #获取加密链接
        k_name = re.compile('"(.*\.key)"').findall(kk[0])[0]
        kk = '\n'+kk[0].replace(k_name,'{}')+'\n'
        try:
            k_val=requests.get(k,headers=head).content.decode('utf-8') #获取key秘钥
            data['aes'] = [kk,'/keys/'+k_val]
        except:
            data['aes'] = [kk,re.compile('.*/').findall(u2)[0]+k_name]
    mu = [x[1] for x in tt]
    murl = max(set(mu),key=mu.count)#根据url去广告
    if mu.count(murl) != len(mu):
        tt_ts = [(float(x[0]),x[2]) for x in tt if x[1]==murl]#ts时间,ts名称[]
    else:
        mt = [x[2][:-7] for x in tt]
        mts = max(set(mt),key=mt.count)#根据名称去广告
        tt_ts = [(float(x[0]),x[2]) for x in tt if x[2][:-7]==mts] if mt.count(mts) !=1 else [(float(x[0]),x[2]) for x in tt]#ts时间,ts名称[]

    data['tt'],dts = list(map(list, zip(*tt_ts)))
    ts = tss(dts[0]) #分析ts切片名称组合
    ts_url = tsu('.',r'.*\.\w+',u2,murl+dts[0]) #获取ts切片链接
    data['host'] = re.compile('.*//.*?/').findall(ts_url)[0] #存储切片host[]
    data['uri'] = re.compile(r'\w/(.*/)').findall(ts_url)[0] #存储切片uri[]
    data['ts'] = ts if ts[:2] != 'aa' else ts.replace('all',json.dumps([x.split('.')[0] for x in dts])) #存储ts切片名称组合[]/全部ts切片名称[]
    data['total'] = round(sum(data['tt']),4) #储存单集总长[]
    data['dur'] = re.compile(r'DURATION:(\d*)').findall(doc)[0] #最大切片时长
    return data

def hls(name,cnname,zu,m3u):
    if len(m3u)==0:return "请填写m3u8下载链接！"
    if zu =='':zu = "最新"
    datas = [name,cnname,zu,'',[],[],[],[],[],[],[],[]] #3.start 4.total 5.aes 6.ts 7.uri 8.tt 9.dur 10.host 11.seg
    res=re.compile(r'http.*?\.m3u8').findall(m3u) #分集m3u8地址
    data = theading(m3u8,res)
    if data==[]:
        return ''
    else:
        [datas[i].append(d[0][v]) for d in data for i,v in zip(range(4,11),['total','aes','ts','uri','tt','dur','host'])]
    datas[3] = time.time() #标记启动时间
    datas[4].append(sum(datas[4])) #[分集，分集,...,全集总长]
    li = lambda x: [x[0]] if len(x)==x.count(x[0]) else x
    datas[6],datas[10] = li(datas[6]),li(datas[10]) #合并ts,host,aes相同值
    aes = list(map(list, zip(*datas[5])))
    datas[5] = [li(aes[0]),li(aes[1])]
    seg = [len(t) for t in datas[8]] #统计分集切片总数
    datas[11] = [sum(seg[:s]) for s in range(len(seg)+1)] #累计从开始到分集切片0的数量
    for d in range(4,12):
        datas[d]=json.dumps(datas[d])
    return datas

def live(name,srs=''):
    db=sql("SELECT * FROM TV WHERE name = '{}';".format(name))
    datas = json.loads(db)[0]
    total = json.loads(datas['total'])
    amount = total.pop() #切片总时长
    runs = time.time() - datas['start'] #运行时长=当前时间-开始时间
    circle = runs // amount #循环播放次数
    if circle>100:
        sql("UPDATE TV SET start={} WHERE name = '{}';".format(time.time(),name))
        return '#EXTM3U\n#EXT-X-VERSION:3\n#reset start time now'
    at = runs % amount #当前循环时长=运行时长 % 全集时长
    pag,n=0,0
    for i,t in enumerate(total): #当前时长递减分集时长
        at = at - t
        if at < 0:
            pag = i
            break
    dd = tsp(datas,pag)
    at = at + total[pag]
    for j,t in enumerate(dd[3]): #当前时长递减切片时长
        at = at - t
        if at < 0:
            n = j
            break 
    txt = '#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-PLAYLIST-TYPE:EVENT\n#EXT-X-TARGETDURATION:{}'.format(json.loads(datas['dur'])[pag])
    if srs == 'vod.m3u8':
        vod = ''
        for p in range(pag,len(total)):
            if p > pag: n,dd = 0,tsp(datas,p)
            ext = dd[2]+'#EXT-X-DISCONTINUITY\n' if n==0 else dd[2]+''
            for nt in range(n,len(dd[3])):
                ext = ext +'\n#EXTINF:{},\n{}{}'.format(dd[3][nt],dd[0],tss(nt,dd[1]))
            vod = vod + ext
        return (txt.replace('EVENT','VOD')+ vod +'\n#EXT-X-ENDLIST').encode('utf-8')

    seg = json.loads(datas['seg'])
    seg = circle*seg.pop()+seg[pag]+n   #当前切片数=循环次数*切片总数+之前分集切片总数+当前切片数
    exd = '#EXT-X-DISCONTINUITY\n' if n==0 and pag==0 else ''
    ext = dd[2]+exd+'#EXT-X-MEDIA-SEQUENCE:{}\n'.format(int(seg)) #存在加密则加入解密标签,初始ts片段
    for nt in range(n,n+3):
        try:
            ext = ext +'\n#EXTINF:{},\n{}{}'.format(dd[3][nt],dd[0],tss(nt,dd[1]))
        except:
            dd = tsp(datas,pag+1) if pag+1<len(total) else tsp(datas,0)
            if nt-n == 2:
                tsn = '#EXTINF:{},\n{}{}'.format(dd[3][0],dd[0],tss(0,dd[1]))
            elif nt-n == 1:
                tsn = '#EXTINF:{},\n{}{}\n#EXTINF:{},\n{}{}'.format(dd[3][0],dd[0],tss(0,dd[1]),dd[3][1],dd[0],tss(1,dd[1]))
            ext = ext +'\n#EXT-X-DISCONTINUITY'+ dd[2] + tsn
            break
    return (txt+ext).encode('utf-8')

def newlive():
    data=[
    'https://ghproxy.net/raw.githubusercontent.com/PizazzGY/TV/master/output/user_result.txt',
    'https://gitee.com/qingyue-yuan/ye/raw/master/TVBox/live.txt',
    'http://mdxgh.tpddns.cn:9999/new/mdzb.txt',
    'http://home.jundie.top:81/Cat/tv/live.txt',
    'http://175.178.251.183:6689/live.txt',
    'http://yuan.haitangw.net/ZB/',
    'https://9xi4o.tk/OneClickRun/live.txt',
    'https://live.zbds.top/tv/iptv4.txt',
    'https://live.zbds.top/tv/iptv6.txt',
    'https://szyyds.cn/tv/live/x.txt',
    'https://bitbucket.org/xduo/duoapi/raw/master/v.txt',
    'https://github.moeyy.xyz/https://raw.githubusercontent.com/lystv/short/main/影视/tvb/MTV.txt',
    'https://g.3344550.xyz/https://raw.githubusercontent.com/SCXSVIP/TV/main/live.txt',
    'https://ghproxy.net/raw.githubusercontent.com/kunkka1986/my.img/main/frjzb240624.txt'
    ]
    for u in data:
        res=requests.get(u,timeout=10)
        if res.status_code==200:
            return res.content.decode('utf-8')
        else:
            continue
    return '链接全部失效'
#--------------------------------------------tv live route------------------------------------
@app.route('/data')
@app.post('/data')
def data(db=''):
    d =dict(request.query.decode("utf-8")) if request.method == 'GET' else request.json
    if type(d) == dict:
        kk=d.keys()
        if 'search' in kk: #关键字搜索
             db="SELECT id,name,cnname,zu FROM TV WHERE cnname like '%{}%';".format(d['search'])
        elif 'auto' in kk: #调取最新数据
            db = "SELECT id,name,cnname,zu FROM TV ORDER BY id DESC LIMIT 50;"
        elif 'id' in kk: #修改数据
            ids= d.pop('id')
            sets=','.join(["{} = '{}'".format(k,v) for k,v in d.items()])
            db="UPDATE TV SET {} WHERE id = {};".format(sets,ids)
        elif 'vacuum' in kk:#收缩数据库
            db = 'VACUUM'
        elif 'm3u' in kk:#初始化m3u8文件
            dd=str(hls(**d)).replace('\\\\','\\')
            db="INSERT INTO TV (name,cnname,zu,start,total,aes,ts,uri,tt,dur,host,seg) VALUES ({});".format(dd[1:-1])
    else: #删除数据
        names=[li['name'] for li in d]
        db="DELETE FROM TV WHERE name IN ({});".format(str(names)[1:-1])
    data=sql(db)
    if data == []:data='提交完成！'
    return data

@app.route('/tvsql')
def tvsql():
    db='''CREATE TABLE TV (
        id   INTEGER      PRIMARY KEY AUTOINCREMENT,
        name   CHAR (20) UNIQUE ON CONFLICT REPLACE,
        cnname CHAR (40),zu   CHAR (20)  NOT NULL,
        start  INTEGER,total  VARCHAR,aes VARCHAR,
        ts   VARCHAR,uri VARCHAR,tt VARCHAR,
        dur VARCHAR,host VARCHAR,seg VARCHAR
    );'''
    sql(db,0)
    return '数据库创建成功!'

@app.route('/keys/<aes>')
def keys(aes):
    return aes

@app.route('/checks')
@app.post('/checks')
def checks():
    vals =dict(request.query.decode("utf-8")) if request.method == 'GET' else request.json
    lines = check(**vals)
    update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())+' 检测完成'
    data = {'update':update,'lives':'\n'.join(lines)}
    return data
    
@app.post('/savetxt')
def savetxt():
    try:
        text = request.forms.get('txt', '')
        if not text: return '文本内容不能为空'
        text = [line+'\n' for line in text.split('\r\n') if line.strip()]
        with open('./static/tv/live/live.txt', 'w', encoding='utf-8') as f:
            f.writelines(text)
    except Exception as e:
        return str(e)
    return '数据修改成功！'

@app.route('/news')
def news(apply=""):
    try:
        first = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(r'./static/tv/live/live.txt')))
        with open('./static/tv/live/live.txt', "r",encoding="utf-8") as file:
            txt = file.read()
        return {'update':first,'lives':txt}
    except:
        return {'update':'无更新','lives':'无数据,请点击自建频道更新'}

@app.route('/live')
def ailive():
    url='https://ghproxy.net/raw.githubusercontent.com/PizazzGY/TV/master/output/user_result.txt'
    response.Content_type='text/html; charset=utf-8'
    res=requests.get(url,timeout=5)
    res=res.content.decode('utf-8') if res.status_code==200 else ''
    with open('./static/tv/live/new.txt',"r",encoding="utf-8") as file:
        txt = file.read() + res
    return txt

@app.route('/newtv')
def newtv():
    db = 'SELECT name,cnname,zu FROM TV;'
    data=json.loads(sql(db))
    data=sorted(data, key=lambda data:data["cnname"],reverse=True)
    db,txt = {},''
    for dd in data:
        zu = '{},#genre#\n'.format(dd['zu'] )
        name = '{},{}/play/{}/index.m3u8\n'.format(dd['cnname'],host,dd['name'])
        name += '{},{}/play/{}/vod.m3u8\n'.format(dd['cnname'],host,dd['name'])
        db[zu] = db[zu] + name if zu in db.keys() else name
    for k,v in db.items():
        txt = txt + k +v
    with open('./static/tv/live/live.txt',"w",encoding="utf-8",newline='\r\n') as flive,open('./static/tv/live/new.txt',"w",encoding="utf-8",newline='\r\n') as fnew:
        flive.write(txt+newlive())
        fnew.write(txt)
    update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    return {'update':update,'lives':txt}

@app.route('/play/<names>/<srs>')
def play(names,srs):
    m3u8=live(names,srs)
    response.headers.update(cross)
    return m3u8

@app.route('/test/<names>')
def test(names):
    if len(names)>1 and names[:4] == "url=":
        url=names[4:]
    else:
        url='../play/{}/index.m3u8'.format(names)
    return player.format(url)

@app.route('/vods')
def vods():
    response.headers.update(cross)
    try:
        url = dict(request.query.decode("utf-8"))['url']
        data=m3u8(url)
        txt = '#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXT-X-TARGETDURATION:{}'.format(data['dur'])
        aes = data['aes']
        if aes != ['no','']:txt = txt + aes[0].format(aes[1])
        u = data['host'] + data['uri']
        for n in range(len(data['tt'])):
            txt = txt +'\n#EXTINF:{},\n{}{}'.format(data['tt'][n],u,tss(n,data['ts']))
        return txt + '\n#EXT-X-ENDLIST'
    except:
        return 'url参数错误'

@app.error(404)
def error404(error):
    return static_file('404.html',root='./static/')

@app.route('/')
@app.route('/<fp:re:.*\.\w+$(?<!\.py)>')
def server_static(fp='index.html'):
    return static_file(fp, root='./static/')

if __name__ == '__main__':
    #第一次需要打开/tvsql初始化数据库
    run(app,host='::',port=88,server="waitress",threads=8,reloader=True,debug=True)
