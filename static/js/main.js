function submitSearch(form) {
  var value = form.input.value.replace(/[^ a-zA-Z0-9_-]/, "")
	if (value != '') {
		window.location.href = "/search/" + value;
	}
  return false;
}

function sendJSON(url, json_data, callback) {
  var xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.responseType = 'json';
  xhr.send(JSON.stringify(json_data));
  xhr.onload = function() {
    var status = xhr.status;
    if (status === 200) {
      callback(null, xhr.response);
    } else {
      callback(status, xhr.response);
    }
  }
}

function createCookie(name,value,days) {
    if (days) {
        var date = new Date();
        date.setTime(date.getTime()+(days*24*60*60*1000));
        var expires = "; expires="+date.toGMTString();
    }
    else var expires = "";
    document.cookie = name+"="+value+expires+"; path=/";
}

function readCookie(name) {
    var nameEQ = name + "=";
    var ca = document.cookie.split(';');
    for(var i=0;i < ca.length;i++) {
        var c = ca[i];
        while (c.charAt(0)==' ') c = c.substring(1,c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
    }
    return null;
}

function eraseCookie(name) {
    createCookie(name,"",-1);
}

function getJSON(url, callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.responseType = 'json';
    xhr.onload = function() {
      var status = xhr.status;
      if (status === 200) {
        callback(null, xhr.response);
      } else {
        callback(status, xhr.response);
      }
    }
    xhr.send();
}

function postAddUser(status, json_response) {
  if (json_response['status'] == 'success') {
    document.getElementById('user-addition-card').innerHTML = '<p>Added to the <a href="/actions">Action Queue</a>! After the Score Saber data has been downloaded, you can search for your Score Saber username.</p>';
  } else {
    document.getElementById('user-addition-card').innerHTML = '<p>It appears you\'ve hit the user addition limit. Please add from the <a href="https://discord.gg/pxWwtWJ">Discord server</a> where we can get a name associated with the request.</p>';
  }
}

function add_user() {
  var value = document.getElementById('user-addition-input').value;
  if (value != '') {
    sendJSON('/api/add_user', {'url': value}, postAddUser);
  }
}

function set_map_pool_cookie(map_pool) {
  createCookie("map_pool", map_pool, 3650)
  window.location.reload(true);
}

function set_announcement(status, json_response) {
  if (json_response['html'] != null) {
    document.getElementById('announcement-card').innerHTML = json_response['html'];
    document.getElementById('announcement-card').style.display = 'block';
  }
}

getJSON('/api/announcement', set_announcement);
