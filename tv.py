#coding:utf-8
from bottle import route,run,static_file,request,post,response,error
import requests,re,json,time,sqlite3,datetime

host='http://127.0.0.1'
head={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.87 Safari/537.36 SE 2.X MetaSr 1.0'}
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
#---------------------------------------------tv live function------------------------------------------------
def sql(db='',tag=1): #tag 0.未建表 1.已建表
    if db=='':return "无操作！"
    sqlite=sqlite3.connect('./tv.db') #连接数据库
    sqlite.row_factory = sqlite3.Row
    try:
        cur=sqlite.cursor()
        data = cur.execute(db).fetchall()
        if len(data) > 0:
            data=json.dumps([dict(d) for d in data])
    except:
        data = "数据变更失败"
    finally:
        sqlite.commit()
        sqlite.close()
    return data

def theading(func,vals,work=4):
    runok = []
    if len(vals)==0:return runok
    import concurrent.futures as futures
    with futures.ThreadPoolExecutor(max_workers=work) as exe:
        threads = {exe.submit(func, url): url for url in vals}
        for thead in futures.as_completed(threads):
            url = threads[thead]
            print('解析：'+url)
            result = (thead.result(),vals.index(url))
            if result:runok.append(result)
    runok.sort(key=lambda x: x[1])  # 根据初始顺序排序
    return runok

def check(txt,fp='0'):   
    def check_url(url): 
        if url.find('#genre#') != -1:return url
        try:
            res = requests.head(url.split(',')[1].strip(),headers=head,timeout=7)
            if res.status_code == 200:
                return url
        except:
            return None
    
    if fp != '1':
        lines = txt.split('\n')
    else:
        with open(txt, "r",encoding="utf8") as file:
            lines = file.readlines()
    runok = theading(check_url,lines,20)
    lines = [url[0] for url in runok]
    if fp == '1':
        with open(txt, "w",encoding="utf8") as file:
            file.writelines(lines)
    return lines

def tss(uts,types='no'): #ts切片序列简化和还原
    tp = types.split("|")
    tp0 = tp[0]
    if tp0=='no':
        ts = uts.split(".")[0]
        ext = uts.split(".")[1]
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
    elif tp0=='nn':
        return '{}.{}'.format(uts,tp[2])
    elif tp0=='mn':
        return "{:0>{}}.{}".format(uts,tp[1],tp[2])
    elif tp0=='sn':
        return tp[1]+"{:0>{}}.{}".format(uts,3,tp[2])
    elif tp0=='an':
        return '{}{}.{}'.format(tp[1],uts,tp[2])
    elif tp0=='aa':
        ts=json.loads(tp[1])
        return '{}.{}'.format(ts[uts],tp[2])

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
    tt = json.loads(data['tt'])[pag]
    ts = json.loads(data['ts'])[pag]
    uri = json.loads(data['uri'])[pag]
    aes = json.loads(data['aes'])[pag]
    aes = '\n' if aes=='no' else '\n'+aes+'\n'
    return [uri,ts,aes,tt]

def m3u8(u):
    data={}
    req = requests.get(u,headers=head,timeout=5)
    if req.status_code == 200:
        doc = req.text
    else:
        return 404
    u2 = tsu('#EXT-X-STREAM-INF','\s(.*m3u8)',u,doc) #判断二级列表
    if u2 != u:doc = requests.get(u2,headers=head,timeout=5).text
    re.compile('(#EXT-X-DISCONTINUITY.*?#EXT-X-DISCONTINUITY)',re.S).sub('\1',doc) #清除广告插入
    vals = re.compile('\s(.*\.[A-z]+.*)\s').findall(doc) #获取key,ts链接
    k = tsu('#EXT-X-KEY','"(.*\.key)"',u2,vals[0]) #判断是否加密
    if k == u2:
        aes = 'no'
    else:
        k_name = re.compile('"(.*\.key)"').findall(doc)[0]
        k_vals = requests.get(k,headers=head) #获取key秘钥
        try:
            k_vals=k_vals.content.decode('utf-8')
            aes = vals.pop(0).replace(k_name,'/keys/'+k_vals)
        except:
            aes = vals.pop(0).replace(k_name,k)
    data['aes'] = aes #存储加密标签[]

    ts_url = tsu('.','.*\.\w+',u2,vals[0]) #获取ts切片链接
    data['uri'] = re.compile('.*/').findall(ts_url)[0] #存储切片uri[]
    ts = tss( re.compile('\w+\.\w+$').findall(ts_url)[0] )
    if ts[:2] == 'aa':
        ts_name = re.compile("(\w*)\.\w+['\"]").findall(str(vals))
        data['ts'] = ts.replace('all',json.dumps(ts_name)) #存储全部ts切片名称[]
    else:
        data['ts'] = ts #存储ts切片名称组合[]
    tts = re.compile(r'#EXTINF:(.*),').findall(doc) #获取全部ts时长
    tts = [float(tt) for tt in tts] #转换为数值
    data['tt'] = tts #存储ts切片时间序列[]
    data['total'] = sum(tts) #储存单集总长[]
    data['dur'] = re.compile(r'DURATION:(\d.*)').findall(doc)[0] #最大切片时长
    return data

def hls(name,cnname,zu,m3u):
    if len(m3u)==0:return "请填写m3u8下载链接！"
    if zu =='':zu = "最新"
    datas = [name,cnname,zu,'',[],[],[],[],[],[],[]] #3.start 4.total 5.aes 6.ts 7.uri 8.tt 9.dur 10.seg
    res=re.compile(r'http.*?\.m3u8').findall(m3u) #分集m3u8地址
    data = theading(m3u8,res)
    if data==[] or data.count(404)>0:
        return 404
    else:
        for d in data:
            for i,v in zip(range(4,11),['total','aes','ts','uri','tt','dur']):
                datas[i].append(d[0][v])
    datas[3] = time.time() #标记启动时间
    datas[4].append(sum(datas[4])) #[分集，分集,...,全集总长]
    seg = [len(t) for t in datas[8]] #统计分集切片总数
    datas[10] = [sum(seg[:s]) for s in range(len(seg)+1)] #累计从开始到分集切片0的数量
    for d in range(4,11):
        datas[d]=json.dumps(datas[d])
    return datas

def live(name):
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
    seg = json.loads(datas['seg'])
    seg = circle*seg.pop()+seg[pag]+n   #当前切片数=循环次数*切片总数+之前分集切片总数+当前切片数
    exd = '#EXT-X-DISCONTINUITY\n' if n==0 and pag==0 else ''
    txt = '#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-PLAYLIST-TYPE:EVENT\n#EXT-X-TARGETDURATION:{}'.format(json.loads(datas['dur'])[pag])
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
#--------------------------------------------tv live route---------------------------------------------------
@post('/checks')
def checks():
    update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = check(**request.json)
    data = json.dumps({'update':update,'lives':'\n'.join(lines)})
    return data
    
@post('/data')
def data():
    d=request.json
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
        elif 'm3u' in kk:#初始化m3u8文件
            dd=str(hls(**d)).replace('\\\\','\\')
            if dd == '404':
                return 404
            else:
                db="INSERT INTO TV (name,cnname,zu,start,total,aes,ts,uri,tt,dur,seg) VALUES ({});".format(dd[1:-1])
    else: #删除数据
        names=[li['name'] for li in d]
        db="DELETE FROM TV WHERE name IN ({});".format(str(names)[1:-1])
    data=sql(db)
    return data 

@route('/mksql')
def mksql():
    db='''CREATE TABLE TV (
        id   INTEGER      PRIMARY KEY AUTOINCREMENT,
        name   VARCHAR (20) UNIQUE ON CONFLICT REPLACE,
        cnname VARCHAR (40),
        zu   CHAR (20)  NOT NULL,
        start  INTEGER,
        total  TEXT,
        aes TEXT,
        ts   TEXT,
        uri TEXT,
        tt   TEXT,
        dur INTEGER,
        seg TEXT
    );'''
    sql(db,0)
    return '数据库创建成功!'

@route('/keys/<aes>')
def keys(aes):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return aes

@route('/news')
def news(apply=""):
    try:
        with open('./static/new.txt', "r",encoding="utf-8") as file:
            lines = file.readlines()
            first = lines[0].strip()[3:-8]
            txt = "".join(lines[1:]).strip()
        return json.dumps({'update':first,'lives':txt})
    except:
        return json.dumps({'update':'无更新','lives':'无数据,请点击自建频道更新'})

@route('/newtv')
def newtv():
    update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    first = '更新：{},#genre#\n'.format(update)
    db='SELECT name,cnname,zu FROM TV'
    data=json.loads(sql(db))
    db,txt = {},''
    for dd in data:
        zu = '{},#genre#\n'.format(dd['zu'] )
        name = '{},{}/play/{}/index.m3u8\n'.format(dd['cnname'],host,dd['name'])
        if zu in db.keys():
            db[zu] = db[zu] + name
        else:
            db[zu] = name
    for k,v in db.items():
        txt = txt + k +v
    with open('./static/new.txt',"w",encoding="utf-8") as file:
        file.write(first+txt)
    return json.dumps({'update':update,'lives':txt})

@route('/play/<names>/index.m3u8')
def play(names):
    m3u8=live(names)
    response.headers.update({
    'Content-Type':'application/x-mpegurl,video/mp2t',
    'Access-Control-Allow-Origin':'*',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Allow-Methods': '*'
    })
    return m3u8

@route('/test/<names>')
def test(names):
    response.headers.update({'Access-Control-Allow-Origin':'*'})
    if len(names)>1 and names[:4] == "url=":
        url=names[4:]
    else:
        url='../play/{}/index.m3u8'.format(names)
    return player.format(url)

@error(404)
def error404(error):
    return static_file('404.html',root='./static/')

@route('/')
@route('/<fp:re:.*\.\w+$(?<!\.py)>')
def server_static(fp='tv.html'):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return static_file(fp, root='./static/')

if __name__ == '__main__':
    #第一次需要打开/mksql初始化数据库,采集站https://ys.urlsdh.com/favorites/%E8%B5%84%E6%BA%90%E9%87%87%E9%9B%86
    run(host='0.0.0.0',port=80,debug=True,server="paste")
