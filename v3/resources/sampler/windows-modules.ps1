param([switch]$IncludeManagement)

# Dot-sourced by the sampler: preferences and imported commands stay in its
# script scope/child scopes, inside this dedicated PowerShell process only.
# Do not discover installed/user modules or depend on a not-yet-loaded cmdlet.
$PSModuleAutoLoadingPreference = 'None'
Import-Module ($PSHOME + '\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -Scope Local -ErrorAction Stop
if ($IncludeManagement) {
    Import-Module ($PSHOME + '\Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -Scope Local -ErrorAction Stop
}
