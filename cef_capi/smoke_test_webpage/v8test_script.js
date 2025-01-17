window.onload = function () {
    // Call the V8 extension functions.
    var a = example.foo();
    if (a != "foo") {
        return;
    }

    // V8 extension functions are OK. Make background green.
    const p = document.getElementById('body_id');
    p.style.backgroundColor = '#008000';
}
