__author__ = 'cyrbuzz'

import re
import os

import asyncio
import pickle

from apiRequestsBase import HttpRequest
from asyncBase import aAsync, toTask
from base import QAction, QMenu, checkFolder, QIcon, QLabel, QObject, RequestThread, QTableWidgetItem, QCursor
from singsFrameBase import PlaylistButton
from netEaseApi import netease
from xiamiApi import xiami
from qqApi import qqApi

import addition


myRequests = HttpRequest()


class ConfigWindow(QObject):

    def __init__(self, window):
        super(ConfigWindow, self).__init__()
        self.window = window

        # 用于存储Tab的历史，方便前后切换。
        # 只存储5个，不考虑效率问题。
        self.history = []
        self.currentIndex = -1
        # 前后切换时也会触发currentChanged信号，
        # 前后切换时不允许增加新的历史也不允许删除旧的历史。
        self.isTab = False

        self.bindConnect()

    def addTab(self, widget, name=''):
        self.window.mainContents.addTab(widget, name)

    def allTab(self):
        return self.window.mainContents.count()

    def addTabHistory(self, index):
        length = len(self.history)
        if not self.isTab:
            if length < 5:
                self.history.append(index)
            else:
                self.history.pop(0)
                self.history.append(index)
            # 不是前后切换时将当前的索引定为末尾一个。
            self.currentIndex = length
        else:
            self.isTab = False

    def bindConnect(self):
        self.window.mainContents.currentChanged.connect(self.addTabHistory)

    def nextTab(self):
        # 后一个的切换。

        if self.currentIndex  == len(self.history)-1 or self.currentIndex == -1:
            return
        else:
            self.isTab = True
            self.currentIndex += 1
            self.window.mainContents.setCurrentIndex(self.history[self.currentIndex])

    def prevTab(self):
        # 前一个的切换。
        if self.currentIndex == 0 or self.currentIndex == -1:
            return
        else:
            self.isTab = True
            self.currentIndex -= 1
            self.window.mainContents.setCurrentIndex(self.history[self.currentIndex])

    def setTabIndex(self, index):
        self.window.mainContents.setCurrentIndex(index)


class ConfigHeader(QObject):
    loginCookiesFolder = 'cookies/headers/loginInfor.cks'
    allCookiesFolder = [loginCookiesFolder]

    def __init__(self, header):
        super(ConfigHeader, self).__init__()
        self.header = header


        self.loginThread = RequestThread(self, None, self.loginFinished)
        self.loginThread.breakSignal.connect(self.emitWarning)

        self.header.loginBox.connectLogin(self.login)
        
        self.loginInfor = {}
        self.result = None
        self.songsDetail = None
        # 用于确定登陆状态。
        self.code = 200
        # 用于确定是否最大化.   
        self.isMax = False

        self.bindConnect()
        self.loadCookies()

    def bindConnect(self):
        self.header.closeButton.clicked.connect(self.header.parent.close)
        self.header.showminButton.clicked.connect(self.header.parent.showMinimized)
        self.header.showmaxButton.clicked.connect(self.showMaxiOrRevert)
        self.header.loginButton.clicked.connect(self.showLoginBox)
        self.header.prevButton.clicked.connect(self.header.parent.config.prevTab)
        self.header.nextButton.clicked.connect(self.header.parent.config.nextTab)
        self.header.searchLine.setButtonSlot(lambda: self.search())

    def showMaxiOrRevert(self):
        if self.isMax:
            self.header.parent.showNormal()
            self.isMax = False
        else:
            self.header.parent.showMaximized()
            self.isMax = True

    @toTask
    def search(self):
        text = self.header.searchLine.text()
        future = aAsync(netease.search, text)
        self.result = yield from future
        if not self.result['songCount']:
            songsIds = []
            self.result['songs'] = []
        else: 
            songsIds = [i['id'] for i in self.result['songs']]

            self.songsDetail = {j:'http{0}'.format(i) for i, j in enumerate(songsIds)}
           
            # 进行重新编辑方便索引。
            songs = self.result['songs']
            self.result['songs'] = [{'name':i['name'], 
            'artists': i['ar'], 
            'picUrl': i['al']['picUrl'],
            'mp3Url': self.songsDetail[i['id']],
            'duration': i['dt'],
            'music_id':i['id']} for i in songs]

        songsCount = self.result['songCount']

        # 总数是0即没有找到。
        if not songsCount:
            songs = []
        else:
            songs = self.result['songs'] 

        self.header.parent.searchArea.setText(text)

        self.header.parent.searchArea.config.setSingsData(songs)

        self.header.parent.config.setTabIndex(3)

    def showLoginBox(self):
        self.header.loginBox.open()

    def login(self):
        informations = self.header.loginBox.checkAndGetLoginInformation()
        
        if not informations:
            return 

        self.loginThread.setTarget(self.loadLoginInformations)
        self.loginThread.setArgs(informations)
        self.loginThread.start()

    def loadLoginInformations(self, informations:tuple):
        result = netease.login(*informations)
        # 网络不通或其他问题。
        if not result:
            self.loginThread.breakSignal.emit('请检查网络后重试~.')
            self.code = 500
            return

        code = result.get('code')
        if str(code) != '200':
            self.loginThread.breakSignal.emit(str(result.get('msg')))
            self.code = 500
            return 

        self.loginInfor = result
        self.code = 200

    def loginFinished(self):
        if str(self.code) == '200': 
            self.header.loginBox.accept()
            self.setUserData()

    @toTask
    def setUserData(self):
        profile = self.loginInfor['profile']
        avatarUrl = profile['avatarUrl']
        self.header.userPix.setSrc(avatarUrl)
        # 加载该账户创建及喜欢的歌单。
        userId = profile['userId']
        future = aAsync(netease.user_playlist, userId)
        data = yield from future

        nickname = profile['nickname']
        self.header.loginButton.setText(nickname)

        self.header.loginButton.clicked.disconnect()
        self.header.loginButton.clicked.connect(self.exitLogin)
        
        self.header.parent.navigation.config.setPlaylists(data)
  
    def emitWarning(self, warningStr):
        self.header.loginBox.setWarningAndShowIt(warningStr)

    def exitLogin(self):
        self.loginInfor = {}
        self.header.loginButton.setText('未登录 ▼')
        self.header.loginButton.clicked.connect(self.showLoginBox)
        self.header.userPix.setSrc('resource/nouser.png')
        self.header.parent.navigation.config.clearPlaylists()

    @checkFolder(allCookiesFolder)
    def saveCookies(self):
        with open(self.loginCookiesFolder, 'wb') as f:
            pickle.dump(self.loginInfor, f)

    @checkFolder(allCookiesFolder)
    def loadCookies(self):
        with open(self.loginCookiesFolder, 'rb') as f:
            self.loginInfor = pickle.load(f)
        self.setUserData()
        self.header.loginButton.clicked.disconnect()
        self.header.loginButton.clicked.connect(self.exitLogin)


class ConfigNavigation(QObject):

    def __init__(self, navigation):
        super(ConfigNavigation, self).__init__()
        self.navigation = navigation
        
        self.detailFrame = self.navigation.parent.detailSings
        # window
        self.mainContents = self.navigation.parent

        self.nativeListFunction = lambda: self.mainContents.mainContents.setCurrentIndex(2)
        self.singsFunction = self.none
        
        self.playlists = []

        self.result = None
        self.singsUrls = None
        self.coverImgUrl = None

        self.api = netease

        self.bindConnect()

    def bindConnect(self):
        self.navigation.navigationList.itemPressed.connect(self.navigationListItemClickEvent)
        self.navigation.nativeList.itemPressed.connect(self.nativeListItemClickEvent)
    
    def navigationListItemClickEvent(self):
        """用户处理导航栏的点击事件。"""
        # 处理其他组件取消选中。
        for i in self.playlists:
            if i.isChecked():
                i.setCheckable(False)
                i.setCheckable(True)
                break

        self.navigation.nativeList.setCurrentRow(-1)

        """处理事件。"""
        self.navigationListFunction()

    def nativeListItemClickEvent(self):
        """本地功能的点击事件。"""
        for i in self.playlists:
            if i.isChecked():
                i.setCheckable(False)
                i.setCheckable(True)
                break

        self.navigation.navigationList.setCurrentRow(-1)

        """处理事件。"""
        self.nativeListFunction()

    def singsButtonClickEvent(self):
        """歌单的点击事件。"""
        self.navigation.navigationList.setCurrentRow(-1)
        self.navigation.nativeList.setCurrentRow(-1)

        """处理事件。"""
        self.singsFunction()

    def setPlaylists(self, datas):
        # 布局原因，需要在最后加一个stretch才可以正常布局。
        # 所以这边先将最后一个stretch删去，将所有的内容添加完成后在加上。
        self.navigation.mainLayout.takeAt(self.navigation.mainLayout.count()-1)
        for i in datas:
            button = PlaylistButton(self, i['id'], i['coverImgUrl'], QIcon('resource/notes.png'), i['name'])
            button.hasClicked.connect(self.startRequest)

            self.playlists.append(button)
            self.navigation.mainLayout.addWidget(button)       
        
        self.navigation.mainLayout.addStretch(1)

    def clearPlaylists(self):
        for i in self.playlists:
            i.deleteLater()

        self.playlists = []

        for i in range(11, self.navigation.mainLayout.count()):
            self.navigation.mainLayout.takeAt(i)

        self.navigation.mainLayout.addStretch(1)

    @toTask
    def startRequest(self, ids, coverImgUrl):
        self.coverImgUrl = coverImgUrl
        self.singsButtonClickEvent()

        future = aAsync(self.api.details_playlist, ids)
        self.result = yield from future
        # 由于旧API不在直接返回歌曲地址，需要获取歌曲号后再次进行请求。
        singsIds = [i['id'] for i in self.result['tracks']]
        # 此处还有些问题。
        # 由于是两次url请求，稍微变得有点慢。
        # future = aAsync(self.api.singsUrl, singsIds)
        # data = yield from future
        # self.singsUrls = {i['id']:i['url'] for i in data}
        # self.singsUrls = [self.singsUrls[i] for i in singsIds]
        self.singsUrls = ['http{0}'.format(i) for i, j in enumerate(singsIds)]

        self.detailFrame.config.setupDetailFrames(self.result, self.singsUrls, singsIds)
        self.detailFrame.picLabel.setSrc(self.coverImgUrl)
        self.detailFrame.picLabel.setStyleSheet('''QLabel {padding: 10px;}''')

        # 隐藏原来的区域，显示现在的区域。
        self.mainContents.mainContents.setCurrentIndex(1)

    def navigationListFunction(self):
        isVisible = self.navigation.parent.mainContent.tab.isVisible()
        if self.navigation.navigationList.currentRow() == 0:
            # 发现音乐。
            self.navigation.parent.mainContents.setCurrentIndex(0)

    def none(self):
        pass


class ConfigMainContent(QObject):

    def __init__(self, mainContent):
        super(ConfigMainContent, self).__init__()
        self.mainContent = mainContent


class ConfigSearchArea(QObject):
    def __init__(self, searchArea):
        super(ConfigSearchArea, self).__init__()

        # current show-table's index.
        self.currentIndex = 0
        # current widgets name。
        self.currentName = '网易云'

        # parent.
        self.searchArea = searchArea
        
        self.transTime = addition.itv2time
        
        self.searchEngineers = {'网易云': netease, '虾米': xiami, 'QQ': qqApi}
        # TODO 
        # to config singsFrameBase instead of configing them respective.
        self.searchResultTableIndexs = {'网易云':self.searchArea.neteaseSearchFrame.singsResultTable, 
            '虾米':self.searchArea.xiamiSearchFrame.singsResultTable , 
            'QQ':self.searchArea.qqSearchFrame.singsResultTable}

        self.musicList = []
        self.noContents = "很抱歉 未能找到关于<font style='text-align: center;' color='#23518F'>“{0}”</font>的{1}。"

        self.bindConnect()
        self.setContextMenu()

    def bindConnect(self):
        self.searchArea.contentsTab.tabBarClicked.connect(self.searchBy)
        self.searchArea.neteaseSearchFrame.singsResultTable.itemDoubleClicked.connect(self.itemDoubleClickedEvent)
        self.searchArea.xiamiSearchFrame.singsResultTable.itemDoubleClicked.connect(self.itemDoubleClickedEvent)
        self.searchArea.qqSearchFrame.singsResultTable.itemDoubleClicked.connect(self.itemDoubleClickedEvent)
        
        self.searchArea.neteaseSearchFrame.singsResultTable.contextMenuEvent = self.contextEvent
        self.searchArea.xiamiSearchFrame.singsResultTable.contextMenuEvent = self.contextEvent
        self.searchArea.qqSearchFrame.singsResultTable.contextMenuEvent = self.contextEvent

    def setContextMenu(self):
        self.actionDownloadSong = QAction('下载', self)
        self.actionDownloadSong.triggered.connect(self.downloadSong)

    @toTask
    def downloadSong(self, x):
        # x is not to use, but must be.
        musicInfo = self.musicList[self.currentIndex]
        url = musicInfo.get('url')
        if 'http:' not in url and 'https:' not in url:
                songId = musicInfo.get('music_id')
                future = aAsync(netease.singsUrl, [songId])
                url = yield from future
                url = url[0].get('url')
                musicInfo['url'] = url
        else:
            url = musicInfo.get('url')

        
        future = aAsync(myRequests.httpRequest, url, 'GET')
        data = yield from future

        if 'downloads' not in os.listdir('.'):
            os.mkdir('downloads')
        
        allMusicName = re.search(r'.*\.[a-zA-Z0-9]+', url[url.rfind('/')+1:]).group(0)
        if allMusicName:

            musicSuffix = allMusicName[allMusicName.rfind('.')+1:]
            musicName = '{name}.{suf}'.format(name=musicInfo.get('name') + ' - ' + musicInfo.get('author'), suf=musicSuffix)
        else:
            # TODO MD5。
            musicName = "random_name.mp3"

        with open('downloads/{musicName}'.format(musicName=musicName), 'wb') as f:
            f.write(data.content)

        self.searchArea.parent.systemTray.showMessage("~~~", '{musicName} 下载完成'.format(musicName=musicName))

    def searchBy(self, index):
        currentWidgetName = self.searchArea.contentsTab.tabText(index)
        self.currentName = currentWidgetName
        self.search(currentWidgetName)

    @toTask
    def search(self, name):
        """接受name信息，由这个引擎进行搜索。"""
        searchEngineer = self.searchEngineers[name]
        data = yield from aAsync(searchEngineer.search, self.searchArea.text)
        if not data['songCount']:
            songsIds = []
            data['songs'] = []
        else: 
            songsIds = [i['id'] for i in data['songs']]

            if name == '网易云':
                songsDetail = {i:'http' for i in songsIds}
            elif name == '虾米' or name == 'QQ':
                songsDetail = {i['id']:i['mp3Url'] for i in data['songs']}

            # 进行重新编辑方便索引。
            songs = data['songs']
            data['songs'] = [{'name':i['name'], 
            'artists': i['ar'], 
            'picUrl': i['al']['picUrl'],
            'mp3Url': songsDetail[i['id']],
            'duration': i['dt'],
            'music_id':i['id'],
            'lyric': i.get('lyric')} for i in songs]

        songsCount = data['songCount']

        # 总数是0即没有找到。
        if not songsCount:
            songs = []
        else:
            songs = data['songs'] 

        self.setSingsData(songs)

    def setSingsData(self, data):
        # 单曲搜索结果。
        searchArea = self.searchArea.contentsTab.currentWidget()
        if not len(data):
            # self.contentsTab.addTab()
            searchArea.noSingsContentsLabel.setText(self.noContents.format(self.searchArea.text, '单曲'))
            searchArea.singsResultTable.hide()
            searchArea.noSingsContentsLabel.show()
        else:
            searchArea.singsResultTable.setRowCount(len(data))

            musicList = []
            for count, datas in enumerate(data):
                picUrl = datas['picUrl']
                url = datas['mp3Url']
                name = datas['name']
                authors = ','.join([t['name'] for t in datas['artists']])
                duration = self.transTime(datas['duration']/1000)
                musicId = datas['music_id']

                searchArea.singsResultTable.setItem(count, 0, QTableWidgetItem(name))
                searchArea.singsResultTable.setItem(count, 1, QTableWidgetItem(authors))
                searchArea.singsResultTable.setItem(count, 2, QTableWidgetItem(duration))
                musicList.append({'url': url, 
                    'name': name, 
                    'time':duration, 
                    'author':authors, 
                    'music_img': picUrl,
                    'music_id': musicId})

            searchArea.noSingsContentsLabel.hide()
            searchArea.singsResultTable.show()

            self.musicList = musicList

    def itemDoubleClickedEvent(self):
        currentRow = self.searchArea.contentsTab.currentWidget().singsResultTable.currentRow()
        data = self.musicList[currentRow]
        self.searchArea.parent.playWidgets.setPlayerAndPlayList(data)

    def contextEvent(self, event):
        currentWidget = self.searchResultTableIndexs.get(self.currentName)
        if not currentWidget:
            return

        item = currentWidget.itemAt(currentWidget.mapFromGlobal(QCursor.pos()))
        self.menu = QMenu(currentWidget)

        self.menu.addAction(self.actionDownloadSong)
        
        try:
            self.currentIndex = item.row() - 1
        # 在索引是最后一行时会获取不到。
        except:
            self.currentIndex = -1

        self.menu.exec_(QCursor.pos())


class ConfigSystemTray(QObject):

    def __init__(self, systemTray):
        super(ConfigSystemTray, self).__init__()
        self.systemTray = systemTray

        self.addActions()
        self.bindConnect()

    def addActions(self):
        closeAction = QAction('退出', self.systemTray, triggered=self.systemTray.parent.close)

        self.systemTray.addAction(closeAction)
        
    def bindConnect(self):
        pass
