let g:vp_max_split_size = 30

hi pytestSuccess ctermfg=40
hi pytestWarning ctermfg=220
hi pytestError ctermfg=196

hi pytestPassed ctermfg=black ctermbg=154
hi pytestFailed ctermfg=white ctermbg=160
hi pytestSkipped ctermfg=black ctermbg=220

hi pytestWaiting ctermfg=white ctermbg=67

hi pytestStage ctermfg=white ctermbg=63

sign define pytest_outcome_passed text=P texthl=pytestPassed
sign define pytest_outcome_failed text=F texthl=pytestFailed
sign define pytest_outcome_error text=E texthl=pytestFailed
sign define pytest_outcome_xpassed text=XP texthl=pytestPassed
sign define pytest_outcome_xfailed text=XF texthl=pytestFailed
sign define pytest_outcome_skipped text=S texthl=pytestSkipped

sign define pytest_collected text=.. texthl=pytestWaiting
sign define pytest_stage_setup text=S> texthl=pytestStage
sign define pytest_stage_call text=C> texthl=pytestStage
sign define pytest_stage_teardown text=T> texthl=pytestStage

nmap <silent><leader>p :VP file<CR>
nmap <silent><leader>f :VP function<CR>
nmap <silent><leader>C :VP cancel<CR>
nmap <silent><F10> :VP toggle<CR>


function! VPEcho(msg, hl)
  let l:msg = []
  if type(a:msg) != type([])
    let l:msg = split(a:msg, "\n")
  else
    let l:msg = a:msg
  endif
  let l:msg = map(l:msg, 'substitute(v:val, "\t", "        ", "")')

  exe 'echohl ' . a:hl
  for line in l:msg
    echom 'Pytest: ' . line
  endfor
  echohl None
endfunction


function! s:VPSetupWindow()
    if winnr("$") == 1
        q
    endif

    setlocal buftype=nowrite
    setlocal bufhidden=wipe
    setlocal nobuflisted
    setlocal noswapfile
    setlocal nowrap
    setlocal filetype=pytest
    setlocal winfixheight
endfunction

autocmd! BufEnter Results.pytest call s:VPSetupWindow()
