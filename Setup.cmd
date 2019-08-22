ECHO OFF
IF EXIST "%~dp0%.git\" (
	ECHO 'Already a git repository present'
) ELSE (
	git clone --depth=1 https://gitlab.tudelft.nl/ivoseverins/traceanalysis.git
	CALL traceanalysis\Libraries.cmd
)
pause
