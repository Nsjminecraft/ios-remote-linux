window.onload = function () {
    // Status check
    function checkStatus() {
        $.getJSON('/status', function (data) {
            var badge = $('#status-badge');
            if (data.connected) {
                badge.text('Connected: ' + (data.device || 'iPhone'));
                badge.removeClass('disconnected').addClass('connected');
            } else {
                badge.text('Disconnected');
                badge.removeClass('connected').addClass('disconnected');
            }
        }).fail(function () {
            $('#status-badge').text('Error').removeClass('connected').addClass('disconnected');
        });
    }
    checkStatus();
    setInterval(checkStatus, 10000);

    // Button handlers
    $(".home").click(function () {
        $.post('/home');
    });
    $(".lock").click(function () {
        $.post('/lock');
    });
    $(".rotation").click(function () {
        $.post('/rotation');
    });
    $(".screenshot").click(function () {
        $.post('/screenshot', function (data) {
            alert('Screenshot saved: ' + data.path);
        });
    });

    // Recording
    $(".record").click(function () {
        $.post('/recording/start', function (data) {
            $('.record').hide();
            $('.stop-record').show();
        });
    });
    $(".stop-record").click(function () {
        $.post('/recording/stop', function (data) {
            $('.stop-record').hide();
            $('.record').show();
            alert('Recording saved');
        });
    });

    // Check recording status on load
    function checkRecordingStatus() {
        $.getJSON('/status', function (data) {
            if (data.recording) {
                $('.record').hide();
                $('.stop-record').show();
            } else {
                $('.stop-record').hide();
                $('.record').show();
            }
        });
    }
    checkRecordingStatus();
    $(".volume-up").click(function () {
        $.post('/button', { data: JSON.stringify({ button: 'volume-up' }) });
    });
    $(".volume-down").click(function () {
        $.post('/button', { data: JSON.stringify({ button: 'volume-down' }) });
    });
    $(".mute").click(function () {
        $.post('/button', { data: JSON.stringify({ button: 'mute' }) });
    });

    // Send text
    $("#main-send").keydown(function (e) {
        if (e.keyCode === 13 && e.ctrlKey) {
            e.preventDefault();
            var content = $(this).val();
            if (content) {
                $.post('/send', { data: JSON.stringify({ text: content }) });
                $(this).val("");
            }
        }
    });

    // Viewer size slider
    $("#size-range").on('input', function () {
        var val = $(this).val();
        $('#viewer-frame').css('height', val + 'vh');
        $("#size-value").text(val + "%");
    });
};
