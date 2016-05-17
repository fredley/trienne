scrolldown = function(){
  $('#messages').scrollTop($('#messages').scrollTop() + 9999);
}

$.fn.putCursorAtEnd = function() {
  return this.each(function() {
    var val = $(this).val();
    $(this).focus().val("").val(val).trigger("change");
    this.scrollTop = 999999;
  });
};

jQuery(document).ready(function($) {

  var VOLUME_QUIET = 0;
  var VOLUME_NORMAL = 1;
  var VOLUME_LOUD = 2;

  var reply_regex = /^:[0-9]+$/;
  var editing = false;
  var edit_id = 0;
  var pincodes = [];
  var ac_index = -1;
  var ac_active = false;

  window.receiveMessage = function(msg) {
    console.log(msg);
    var msg = JSON.parse(msg);
    switch(msg.type){
      case "msg":
        appendFastMessage(msg);
        break;
      case "vote":
        var message = $("#medium .msg-" + msg.id).parent();
        message.find('.score').text(msg.content);
        break;
      case "hotness":
        // reorder by id, fetch those we haven't got any more...?
        $('#medium').addClass('loading');
        var hotlist = $('<div></div>');
        msg.posts.forEach(function(post){
          var p = $('#medium').find('.msg-' + post.id).parent();
          hotlist.append(p);
        });
        $('#medium').html(hotlist);
        $('#medium').removeClass('loading');
        break;
      case "pin":
        var message = $("#messages .msg-" + msg.id);
        if ($('#medium').find('.msg-' + msg.id).length === 0) {
          insertMediumMessage(message.clone(true),{
            name: message.parent().find(".author").text(),
            id: msg.id
          });
        }
        el = $('#medium').find('.msg-' + msg.id).parent();
        el.find('.score').text(msg.score);
        el.find('.edited').removeClass('edited');
        var idx = pincodes.indexOf(msg.pincode);
        if (msg.author_id == my_id){
          el.find('.vote').addClass('disabled');
        }
        if (idx >= 0) {
          if (msg.author_id != my_id){
            markVoted(el.find('.votes'), 1);
          }
          pincodes.splice(idx,1);
        }
        $('#medium').scrollTop(0);
        break;
      case "unpin":
        $("#medium .msg-" + msg.id).parent().remove();
        break;
      case "edit":
        var parsed = parseReply(msg.content);
        var msg = $('.msg-' + msg.id);
        msg.addClass('edited')
        .attr('data-raw', msg.raw)
        .find('.content').html(parsed.content);
        var ping = msg.content.indexOf("@" + my_name) >= 0;
        if(volume > VOLUME_QUIET && ping){
          author = msg.parent().find('.author');
          img = author.find("img").attr("src");
          notify(author.text() + ": " + text, img);
        }
        break;
      case "status":
        if($('.user-' + msg.id).length > 0){
          $('.user-' + msg.id).find('.online-marker').attr('class', 'online-marker').addClass("status-" + msg.status);
        } else {
          var user = $('<div class="user user-' + msg.id + '"></div>').text(msg.username);
          user.prepend('<img src="' + msg.img + '" alt="">');
          user.append('<div class="online-marker status-' +  msg.status + '"></div>');
          $('#users').append(user);
        }
        break;
      case "delete":
        $(".msg-" + msg.id).addClass('deleted').find(".content").html("(deleted)");
        $("#medium .msg-" + msg.id).parent().remove();
        break;
      case "flag":
        $(".msg-" + msg.id).addClass('flagged');
    }
  };

  var loading = true;

  var sock = WS4Redis({
    uri: sock_uri,
    receive_message: receiveMessage,
    heartbeat_msg: hb
  });

  var temp_vol = volume;
  volume = VOLUME_QUIET;
  post_history.forEach(appendFastMessage);
  pinned.forEach(function(el){
    insertMediumMessage(createMessage(el,true), el.author, el);
  });
  volume = temp_vol;
  if(!can_participate){
    $("#shout").attr("disabled","disabled").addClass("disabled");
  }
  loading = false;

  $("#shout").keydown(function(ev) {
    if (ev.keyCode === 13 && !ev.shiftKey) {
      ev.preventDefault();
      if(ac_active){
        stopAutocomplete();
        return;
      }
      var message = shout.val();
      if (message.trim() !== ""){
        if(editing) {
          $.ajax({
            method: "post",
            url: "/post/" + edit_id + "/edit/",
            data: {
              message: message
            }
          });
          stopEdit();
        } else {
          $.ajax({
            method: "post",
            url: "/room/" + room_id + "/post/",
            data: {
              message: message
            },
            error:function(response){
              var data = JSON.parse(response.responseText);
              console.log(data);
              showError(data.message);
            }
          });
        }
        shout.val("");
      }
    }else if (ev.keyCode === 9) { //tab
      ev.preventDefault();
      if(ac_active){
        var amount = (ev.shiftKey) ? -1 : 1;
        updateAutoComplete(amount);
        return;
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
    stopAutocomplete();
  });

  $("#shout").keyup(function(ev) {
    if(!ac_active){
      var words = $(this).val().split(' ');
      var last = words[words.length - 1];
      if (last.length > 1 && last[0] === '@'){
        var search = last.substring(1).toLowerCase();
        var names = [];
        $('.user').not('.me').each(function(el){
          var name = $(this).text().trim().toLowerCase();
          if (name.indexOf(search) >= 0){
            names.push(name);
          }
        });
        if(names.length > 0){
          startAutocomplete(names);
        }
      }
    }
  });

  // TODO: make this generic

  $('#add-member').on('keydown', function(ev){
    if(ev.keyCode === 40) { // down arrow
      // select next
      ev.preventDefault();
      var selected = $('.result.selected');
      if (selected.length === 0){
        var el = $('.result').first();
        el.addClass('selected');
        $(this).val(el.text());
      }else{
        var el = selected.next();
        if(el.length){
          el.addClass('selected');
          $(this).val(el.text());
          selected.removeClass('selected');
        }
      }
    }else if(ev.keyCode === 38) { //up arrow
      // select previous
      ev.preventDefault();
      var selected = $('.result.selected');
      if (selected.length !== 0){
        var el = selected.prev();
        if(el.length){
          el.addClass('selected');
          $(this).val(el.text());
        }
        selected.removeClass('selected');
      }
    }else if(ev.keyCode === 27 && editing) { // escape
      $('#user-results').html('');
    }else if (ev.keyCode === 13) { //return
      // submit
      ev.preventDefault();
      $(this).attr('disabled','disabled');
      var self = $(this);
      var username = $(this).val();
      $('#user-results').html('');
      $.ajax({
        method:'post',
        url:'/room/' + room_id + '/add_member/',
        data:{
          username: username
        },
        success:function(data){
          self.val('');
          self.removeAttr('data-id');
          self.parent().addClass('has-success');
          var user = $('<div class="user user-' + data + '"></div>').text(username);
          user.prepend('<span class="online-marker">&bull;</span>');
          $('#users').append(user);
        },
        error:function(){
          self.parent().addClass('has-error');
        },
        complete:function(){
          self.removeAttr('disabled');
        }
      });
    }else{
      var val = $(this).val() + String.fromCharCode(ev.keyCode);
      if(val !== ""){
        $.ajax({
          method: 'get',
          url: '/ajax/users/c/',
          data: {
            org: org,
            s: val
          },
          success: function(data){
            $('#user-results').html('');
            for (var i in data.results){
              $('#user-results').append('<div class="result" data-id="' + data.results[i].id + '">' + data.results[i].username + '</div>')
            }
          }
        });
      }
    }
  });

  function startAutocomplete(names){
    ac_active = true;
    $('#autocomplete').html('');
    for(var i=0; i<names.length; i++){
      var el = $('<div class="ac">' + names[i] + '</div>');
      if (i === ac_index){
        el.addClass('active');
      }
      $('#autocomplete').append(el);
    }
  }

  function updateAutoComplete(amnt){
    ac_index = (ac_index + amnt) % $('.ac').length;
    $('.ac').removeClass('active');
    $('.ac:eq(' + ac_index + ')').addClass('active');
    var words = $('#shout').val().split(' ');
    words[words.length - 1] = '@' + $('.ac.active').text();
    $('#shout').val(words.join(' '));
  }

  function stopAutocomplete(){
    $('#autocomplete').html('');
    ac_index = -1;
    ac_active = false;
  }

  function showError(msg){
    var error = $('<div class="error">' + msg + '</div>');
    $('#entry').append(error);
    error.fadeIn('slow');
    setTimeout(function(){
      error.fadeOut('slow', function(){
        error.remove();
      });
    }, 2000);
  }

  function startEdit(el){
    stopEdit();
    el.addClass('editing');
    edit_id = el.attr('data-id');
    editing = true;
    shout.addClass('editing');
    var val = shout.val();
    shout.val(el.attr('data-raw'));
    shout.putCursorAtEnd();
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
    $('.editing').removeClass('editing');
    editing = false;
    edit_id=0;
    shout.removeClass('editing');
  }

  $(".volume").on('click', function(){
    var self = $(this);
    if(self.hasClass('active')){ return; }
    $.ajax({
      url:"/room/" + room_id + "/prefs/",
      data:{volume:self.attr('data-volume')},
      method:'post',
      success:function(){
        $('.volume').removeClass('active');
        self.addClass('active');
        volume = parseInt(self.attr('data-volume'));
      }
    });
  });

  function notify(text, image) {
    if ("Notification" in window) {
      if (Notification.permission === "granted") {
        text = text.replace(/&#([0-9]{1,3});/gi, function(match, numStr) {
          // parse html entities http://stackoverflow.com/a/7394814/319618
          var num = parseInt(numStr, 10);
          return String.fromCharCode(num);
        });
        image = image.replace('s=32','s=128');
        var opts = {
          body: text,
          icon: image
        }
        var notification = new Notification("Lanes", opts);
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
      content = '<i class="fa fa-share fa-flip-x"></i> @' +
              to + ' ' + text;
    } else {
      text = content;
    }
    return {text: text, to: to, reply_to: reply_to, content: content};
  }

  function createMessage(msg) {
    var mine = msg.author.id == my_id;
    var id = msg.id;
    var parsed = parseReply(msg.content);
    var text = parsed.text;
    var to = parsed.to;
    var reply_to = parsed.reply_to;
    var pinged = parsed.text.indexOf("@" + my_name) >= 0;
    if (!loading && !mine && (volume == VOLUME_LOUD || ((to == my_name || pinged) && volume > VOLUME_QUIET))){
      notify(msg.author.name + ": " + text, msg.author.img);
    }
    var message = $('<div class="message"></div>')
      .append($('<div class="content"></div>').html(parsed.content));
    var controls = $('<div class="controls"></div>');
    var flag = $('<i class="fa fa-flag-o flag"></i>');
    flag.on('click', function(){
      $.ajax({
        method: "post",
        url: "/post/" + id + "/flag/"
      });
      $(this).remove();
    });
    controls.append(flag);
    if (mine || is_admin) {
      var link = $('<div class="link"><i class="fa fa-link"></i></div>');
      link.on('click', function(){
        var win = window.open('/post/' + id + '/history/', '_blank');
        if(win){
          win.focus();
        }
      });
      message.prepend(link);
      var edit = $('<i class="fa fa-pencil edit"></i>');
      edit.on('click',function(){
        startEdit($(this).parent().parent());
      });
      controls.append(edit);
    }
    var pin = $('<i class="fa fa-thumb-tack pin"></i>');
    pin.on('click', function(){
      var code = Math.random().toString(36);
      pincodes.push(code);
      $.ajax({
        method: "post",
        url: "/room/" + room_id + "/pin/",
        data: {
          id: id,
          pin: true,
          pincode: code
        }
      });
    });
    controls.append(pin);
    if (!mine){
      var reply = $('<i class="fa fa-share fa-flip-y reply"></i>');
      reply.on('click', function(){
        var first = shout.val().split(' ')[0];
        var val;
        if (reply_regex.test(first)) {
          val = shout.val().split(' ').splice(1).join(' ');
        } else {
          val = shout.val();
        }
        shout.val(":" + id + " " + val);
        shout.putCursorAtEnd();
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
    if(msg.deleted){
      message.addClass("deleted");
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
    if(!loading){
      $('.user-' + msg.author.id).find('.online-marker').addClass('online');
    }
    return message;
  }

  function insertFastMessage (message, author) {
    // Is the last post by the same author? If so, concat
    var last = $('#messages .message-group').last();
    if (last.attr('data-id') == author.id){
      last.append(message);
    } else {
      var group = $('<div class="message-group clearfix"></div>')
        .append($('<div class="author"></div>').text(author.name)
          .prepend('<img src="' + author.img + '" alt="" class="profile-picture">'))
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
    var count = $('#messages .message').length;
    if(count > 100) {
      var to_remove = count - 100;
      for(var i = 0; i < to_remove; i++){
        var to_remove = $('#messages .message').first();
        var parent = to_remove.parent();
        var remove_parent = parent.find(".message").length === 1;
        to_remove.remove();
        if (remove_parent){
          parent.remove();
        }
      }
    }
  }

  function submitVote (value, id, el) {
    $.ajax({
        method: 'post',
        url: "/post/" + id + "/vote/",
        data: {
          value: value
        },
        success: function(){
          markVoted(el, value);
        }
      });
  }

  function markVoted(el, value) {
    if (value === 1) {
      el.find('.upvote .fa').addClass('active');
    } else {
      el.find('.dnvote .fa').addClass('active');
    }
    el.addClass('voted');
  }

  function insertMediumMessage (message, author, extras) {
    var upvote = $('<div class="vote upvote"><i class="fa fa-caret-up"></i></div>');
    var dnvote = $('<div class="vote dnvote"><i class="fa fa-caret-down"></i></div>');
    var score = $('<div class="score">0</div>');
    if (author.id === my_id) {
      upvote.addClass('disabled');
      dnvote.addClass('disabled');
    } else {
      upvote.on('click',function(){
        submitVote(1, message.attr('data-id'), $(this).parent());
        $(this).parent().find('.vote').off();
      });
      dnvote.on('click',function(){
        submitVote(-1, message.attr('data-id'), $(this).parent());
        $(this).parent().find('.vote').off();
      });
    }
    var votes = $('<div class="votes"></div>').append(upvote).append(dnvote).append(score);
    if (extras) {
      score.text(extras.score);
      if (extras.vote === 1) {
        upvote.find(".fa").addClass("active");
        votes.addClass("voted");
      } else if (extras.vote === -1) {
        dnvote.find(".fa").addClass("active");
        votes.addClass("voted");
      }
    }
    $('#medium').prepend($('<div class="message-group clearfix"></div>')
        .append($('<div class="author"></div>').text(author.name))
        .attr('data-id', author.id)
        .append(message)
        .append(votes));
    $('.msg-' + message.attr('data-id')).addClass('pinned');
  }
});
