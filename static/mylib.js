$(function() {
    $("#tabs").tabs();
});

function fileSelected() {
    var file = document.getElementById('file').files[0];
    if (file) {
        var fileSize = 0;
        if (file.size > 1024 * 1024)
            fileSize = (Math.round(file.size * 100 / (1024 * 1024)) /
                        100).toString() + 'MB';
        else
            fileSize = (Math.round(file.size * 100 / 1024) /
                        100).toString() + 'KB';

        document.getElementById('filename').innerHTML =
            'Name: ' + file.name;
        document.getElementById('filesize').innerHTML =
            'Size: ' + fileSize;
        document.getElementById('filetype').innerHTML =
            'Type: ' + file.type;
    }
}

function uploadFile() {
    var fd = new FormData();
    fd.append('file', document.getElementById('file').files[0]);

    var req = new XMLHttpRequest();
    req.upload.addEventListener('progress', uploadProgress, false);
    req.addEventListener('load', uploadComplete, false);
    req.addEventListener('error', uploadFailed, false);
    req.addEventListener('abort', uploadCanceled, false);

    req.open('post', '/upload');
    req.send(fd);
}

/**
 * Event handlers
 */
function uploadProgress(evt) {
    if (evt.lengthComputable) {
        var percentComplete = Math.round(evt.loaded * 100 / evt.total);
        document.getElementById('progressNumber').innerHTML =
            percentComplete.toString() + '%';
    } else {
        document.getElementById('progressNumber').innerHTML =
            'unable to compute';
    }
}

function uploadComplete(evt) {
    alert(evt.target.responseText);
}

function uploadFailed(evt) {
    alert('An error attempting to upload the file.');
}

function uploadCanceled(evt) {
    alert('Canceled by the user or the browser dropped the connection.');
}

/*
 * Tabbed pane
 */
