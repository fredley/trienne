scrolldown = function(){
  $('#messages').scrollTop($('#messages').scrollTop() + 9999);
}

jQuery(document).ready(function($) {

  var VOLUME_QUIET = 0;
  var VOLUME_NORMAL = 1;
  var VOLUME_LOUD = 2;

  var reply_regex = /^:[0-9]+$/;
  var editing = false;
  var edit_id = 0;

  var sock = WS4Redis({
    uri: sock_uri,
    receive_message: receiveMessage,
    heartbeat_msg: hb
  });

  var temp_vol = volume;
  volume = VOLUME_QUIET;
  post_history.forEach(appendFastMessage);
  pinned.forEach(function(el){
    insertMediumMessage(createMessage(el,true), el.author);
  });
  volume = temp_vol;


  $("#shout").keydown(function(ev) {
    if (ev.keyCode === 13 && !ev.shiftKey) {
      ev.preventDefault();
      var message = shout.val();
      if (message.trim() !== ""){
        if(editing) {
          $.ajax({
            method: "post",
            url: urls.edit,
            data: {
              id: edit_id,
              message: message
            }
          });
          stopEdit();
        } else {
          $.ajax({
            method: "post",
            url: urls.post,
            data: {
              message: message
            }
          });
        }
        shout.val("");
      }
    }else if(ev.keyCode === 38) { //up arrow
      // select previous message for editing
      ev.preventDefault();
      var el;
      if(!editing) {
        el = $('.mine .message').last();
      } else {
          el = getNextEdit(-1);
          if(!el){
            return;
          }
      }
      startEdit(el);
    }else if(ev.keyCode === 40) { // down arrow
      // select next message for editing, if possible
      if(editing){
        ev.preventDefault();
        el = getNextEdit(1);
        if(!el){
          stopEdit();
          return;
        }
        startEdit(el);
      }
    }else if(ev.keyCode === 27 && editing) { // escape
      stopEdit();
    }
  });

  function startEdit(el){
    stopEdit();
    el.addClass('editing');
    edit_id = el.attr('data-id');
    editing = true;
    shout.addClass('editing');
    shout.focus().val("").val(el.attr('data-raw'));
  }

  function getNextEdit(increment) {
    var current_index = $('.mine .message').index($('.mine .message.editing'));
    var next_index = current_index + increment;
    if (current_index + increment < 0 || current_index + increment > $('.mine .message').length - 1){
      return false;
    }else{
      return $($('.mine .message')[next_index]);
    }
  }

  function stopEdit(){
    shout.val("");
    $('.mine .message').removeClass('editing');
    editing = false;
    edit_id=0;
    shout.removeClass('editing');
  }

  $(".volume").on('click', function(){
    var self = $(this);
    if(self.hasClass('active')){ return; }
    $.ajax({
      url:urls.prefs,
      data:{volume:self.attr('data-volume')},
      method:'post',
      success:function(){
        $('.volume').removeClass('active');
        self.addClass('active');
        volume = parseInt(self.attr('data-volume'));
      }
    });
  });

  function notify(text) {
    if ("Notification" in window) {
      if (Notification.permission === "granted") {
        var notification = new Notification(text);
      }else if (Notification.permission !== 'denied') {
        Notification.requestPermission(function(){
          notify(text);
        });
      }
    }
  }

  function parseReply(content) {
    var to = "";
    var text = "";
    var reply_to = 0;
    if(reply_regex.test(content.split(' ')[0])) {
      reply_to = content.split(' ')[0].split(":")[1];
      to = $('.msg-' + reply_to).attr('data-author');
      text = content.split(' ').splice(1).join(' ');
      //TODO if not found, get
      content = '<i class="glyphicon glyphicon-share-alt glyphicon-flip-x"></i> @' +
              to + ' ' + text;
    } else {
      text = content;
    }
    return {text: text, to: to, reply_to: reply_to, content: content};
  }

  function createMessage(msg, mute=false) {
    var mine = msg.author.id == my_id;
    var id = msg.id;
    var parsed = parseReply(msg.content);
    if (reply_to)
    var text = parsed.text;
    var to = parsed.to;
    var reply_to = parsed.reply_to;
    if (!mute && !mine && (volume == VOLUME_LOUD || (to == my_name && volume > VOLUME_QUIET))){
      notify(msg.author.name + ": " + text);
    }
    var message = $('<div class="message"></div>')
      .append($('<div class="content"></div>').html(parsed.content));
    var controls = $('<div class="controls"></div>');
    if (mine || is_admin) {
      var edit = $('<i class="glyphicon glyphicon-pencil edit"></i>');
      edit.on('click',function(){
        startEdit($(this).parent().parent());
      });
      controls.append(edit);
    }
    if (!mine || is_admin) {
      var pin = $('<i class="glyphicon glyphicon-pushpin pin"></i>');
      pin.on('click', function(){
        $.ajax({
          method: "post",
          url: urls.pin,
          data: {
            id: id,
            pin: true
          }
        });
      });
      controls.append(pin);
    }
    if (!mine){
      var reply = $('<i class="glyphicon glyphicon-share-alt glyphicon-flip-y reply"></i>');
      reply.on('click', function(){
        var first = shout.val().split(' ')[0];
        var val;
        if (reply_regex.test(first)) {
          val = shout.val().split(' ').splice(1).join(' ');
        } else {
          val = shout.val();
        }
        shout.val(":" + id + " " + val);
        shout.focus();
      });
      controls.append(reply);
    }
    message.append(controls);
    message.addClass("msg-" + id);
    message.attr("data-raw", msg.raw);
    message.attr("data-id", id);
    message.attr("data-author", msg.author.name);
    message.attr("data-targets","");
    if(msg.edited){
      message.addClass("edited");
    }
    if(reply_to > 0){
      message.attr("data-targets",reply_to);
      var target = $('.msg-' + reply_to);
       target.attr("data-targets", target.attr("data-targets") + "," + id);
    }
    message.hover(function(){
      $(this).attr("data-targets").split(",").forEach(function(target){
        $('.msg-' + target).addClass('highlight');
      });
    }, function(){
      $(this).attr("data-targets").split(",").forEach(function(target){
        $('.msg-' + target).removeClass('highlight');
      });
    });
    return message;
  }

  function insertFastMessage (message, author) {
    // Is the last post by the same author? If so, concat
    var last = $('#messages .message-group').last();
    if (last.attr('data-id') == author.id){
      last.append(message);
    } else {
      var group = $('<div class="message-group clearfix"></div>')
        .append($('<div class="author"></div>').text(author.name))
        .attr('data-id', author.id)
        .append(message);
       if(author.id == my_id) {
         group.addClass("mine");
       }
      $('#messages').append(group);
    }
    scrolldown();
  }

  function appendFastMessage (msg) {
    if($('#messages .msg-'+msg.id).length === 0){
      insertFastMessage(createMessage(msg), msg.author);
    }
  }

  function insertMediumMessage (message, author) {
    $('#medium').prepend($('<div class="message-group clearfix"></div>')
        .append($('<div class="author"></div>').text(author.name))
        .attr('data-id', author.id)
        .append(message));
    $('.msg-' + message.attr('data-id')).addClass('pinned');
  }

  function receiveMessage(msg) {
    console.log(msg);
    var msg = JSON.parse(msg);
    if (msg.type == "msg"){
      appendFastMessage(msg);
    } else if (msg.type == "edit") {
      var parsed = parseReply(msg.content);
      $('.msg-' + msg.id)
      .addClass('edited')
      .attr('data-raw', msg.raw)
      .find('.content').html(parsed.content);
    }  else if (msg.type == "pin") {
      if (msg.action == "pin") {
        var message = $("#messages .msg-" + msg.content);
        if ($('#medium').find('.msg-' + msg.content).length === 0) {
          insertMediumMessage(message.clone(true),{
            name: message.parent().find(".author").text(),
            id: message.parent().attr("data-id")
          });
        }
      } else if (msg.action == "unpin") {
        var message = $("#medium .msg-" + msg.content);
        message.remove();
        $('.msg-' + msg.content).removeClass('pinned');
      }
    }
  }
});