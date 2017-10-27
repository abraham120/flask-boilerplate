var term = [];
var socket = io(location.origin + '/term', {path: '/socket.io'})
var buf = ['', ''];

function Wetty(argv) {
    this.argv_ = argv;
    this.io = null;
    this.pid_ = -1;
}

Wetty.prototype.run = function() {
    this.io = this.argv_.io.push();

    this.io.onVTKeystroke = this.sendString_.bind(this);
    this.io.sendString = this.sendString_.bind(this);
    this.io.onTerminalResize = this.onTerminalResize.bind(this);
}

Wetty.prototype.sendString_ = function(str) {
    if (this.io.terminal_.div_.id == "Console1") {
        node = 0;
    } else {
        node = 1;
    }
    socket.emit('input', {'node':node, 'data':str});
    //console.log('input');
};

Wetty.prototype.onTerminalResize = function(col, row) {
    socket.emit('resize', { col: col, row: row });
};

socket.on('connect', function() {
    lib.init(function() {
        hterm.defaultStorage = new lib.Storage.Local();
        for (i = 0; i < 2; i++) {
            term[i] = new hterm.Terminal();
            window.term[i] = term[i];
            term[i].decorate(document.getElementById('Console'+(i+1)));

            term[i].setCursorPosition(0, 0);
            term[i].setCursorVisible(true);
            term[i].prefs_.set('ctrl-c-copy', true);
            term[i].prefs_.set('ctrl-v-paste', true);
            term[i].prefs_.set('use-default-window-copy', true);

            term[i].runCommandClass(Wetty, document.location.hash.substr(1));
            socket.emit('resize', {
                col: term[i].screenSize.width,
                row: term[i].screenSize.height
            });

            if (buf[i] && buf[i] != '')
            {
                term[i].io.writeUTF16(buf[i]);
                buf[i] = '';
            }

            term[i].setFontSize(12);
        }
    });
});

socket.on('output', function(data) {
    if (!term[data.node]) {
        buf[data.node] += data.buf;
        return;
    }
    term[data.node].io.writeUTF16(data.buf);
});

socket.on('disconnect', function() {
    console.log("Socket.io connection closed");
});
