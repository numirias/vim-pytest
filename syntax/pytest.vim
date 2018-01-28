if exists("b:current_syntax")
    finish
endif

syn match pytestError "\v^[>]"
syn match pytestError "\v^[E].*$"
highlight link pytestError Error

syn region pytestSection start=/\v^\=/ end=/\v\=$/ keepend
highlight link pytestSection Statement

syn region pytestSubSection start=/\v^[_]+ / end=/\v$/ keepend
highlight link pytestSubSection Identifier

syn region pytestSubSection2 start=/\v^(_ )+/ end=/\v$/ keepend
highlight link pytestSubSection2 Comment

syn region pytestSubSection3 start=/\v^-+ / end=/\v-$/ keepend
highlight link pytestSubSection3 Comment

syn include @pyth syntax/python.vim
syn region pytestPython start=/\v^[ >]   / end=/\v^[^ >]@=/ contains=@pyth,pytestError skipwhite keepend

let b:current_syntax = "pytest"
