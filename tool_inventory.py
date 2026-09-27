"""Optional OS executable inventory. Presence does not imply configuration or permission."""

KALI_TOOLSET = {
    "Information Gathering & OSINT": [
        "metagoofil", "spiderfoot", "spiderfoot-cli", "email2phonenumber", 
        "emailharvester", "instaloader", "linkedin2username", "photon", 
        "sherlock", "tookie-osint", "theHarvester"
    ],
    "Vulnerability Analysis & Network Scanning": [
        "amass", "autorecon", "dmitry", "legion", "nmap", "zenmap", 
        "unicornscan", "masscan", "sctpscan", "ike-scan", "sslscan", 
        "sslyze", "tlssled", "snmp-check", "braa", "onesixtyone"
    ],
    "DNS Assessment": [
        "dnsmap", "dnsrecon", "dnsenum", "massdns", "dnstracer", "dnswalk"
    ],
    "Web Application Analysis": [
        "assetfinder", "arjun", "dirb", "dirbuster", "dirsearch", "feroxbuster", 
        "ffuf", "finalrecon", "findomain", "gobuster", "gospider", "lbd", 
        "parsero", "recon-ng", "subfinder", "sublist3r", "uniscan-gui", 
        "urlcrazy", "uro", "wfuzz", "wpprobe", "CAT", "gvm-start", 
        "heartleech", "owasp-mantra-ff", "burpsuite", "caido", "caido-cli", 
        "crlfuzz", "davtest", "joomscan", "nikto", "nuclei", "paros", 
        "skipfish", "sstimap", "subjack", "tinja", "wapiti", "watobo", 
        "wcvs", "webscarab", "whatweb", "wpscan", "zaproxy"
    ],
    "Wireless, Bluetooth & RF": [
        "bettercap", "bluelog", "bluesnarfer", "btscanner", "blueranger", 
        "fang", "spooftooph", "ubertooth-util", "asleap", "kismet", 
        "sparrow-wifi", "wash", "hackrf_info", "gnuradio", "gqrx", 
        "chirp", "rfcat", "aircrack-ng", "airgeddon", "bully", "cowpatty", 
        "eapmd5pass", "fern-wifi-cracker", "freeradius", "pixiewps", 
        "reaver", "wifi-honey", "wifiphisher", "wifite"
    ],
    "Development & Reverse Engineering": [
        "code-oss", "donut", "sickle-pdk", "wixl", "wmic", "wmis", 
        "pyinstaller", "olevba", "olefile", "afl-fuzz", "bed", 
        "generic_chunked", "generic_listen_tcp", "generic_send_tcp", 
        "generic_send_udp", "sfuzz", "msf-nasm_shell", "msfvenom", 
        "msfpc", "shellnoob", "clang", "clang++", "edb", "ollydbg", 
        "gef", "gdb", "cstool", "ghidra", "radare2", "rizin", "cutter", 
        "recstudio", "recstudio-cli", "apktool", "bytecode-viewer", 
        "jadx-gui", "javasnoop", "jd-gui", "d2j-dex2jar"
    ],
    "Exploitation, Frameworks & C2": [
        "pompem", "searchsploit", "exploitdb-papers", "dns-rebind", 
        "gophish-start", "setoolkit", "metasploit-framework", "sqlmap", 
        "sqlninja", "sqlsus", "jsql", "commix", "jboss-linux", "jboss-win", 
        "armitage", "evilgrade", "beef-xss-start", "xsser", "nishang", 
        "powersploit", "adaptixclient", "adaptixserver", "havoc", 
        "hoaxshell", "koadic", "powershell-empire", "starkiller-start", 
        "villain"
    ],
    "Post-Exploitation & Maintaining Access": [
        "laudanum", "phpggc", "seclists", "webacoo", "webshells", 
        "weevely", "backdoor-factory", "cymothoa", "lynis", "peass", 
        "linpeas", "winpeas", "unix-privesc-check", "bloodyad", 
        "crackmapexec", "evil-winrm", "evil-winrm-py", "impacket-scripts", 
        "mimikatz", "netexec", "passing-the-hash", "rubeus", "smbmap", 
        "xfreerdp3", "impacket-smbexec", "impacket-psexec", "rdesktop"
    ],
    "Evasion, Sniffing & Spoofing": [
        "sniffjoke", "ftest", "fragrouter", "macchanger", "outguess", 
        "steghide", "stegosuite", "stegsnow", "shellter", "veil", 
        "ccrypt", "padbuster", "above", "arpspoof", "darkstat", 
        "dnschef", "driftnet", "dsniff", "hexinject", "netsniff-ng", 
        "wireshark", "scapy", "tcpdump", "tcpflow", "arping", "arpwatch", 
        "atk6-thcping6", "fierce", "fping", "hping3", "iputils-arping", 
        "p0f", "ettercap-text-only", "ettercap", "evilginx2", "fiked", 
        "fluxion", "mitmproxy", "mitm6", "ssldump", "sslsplit", "sslsniff", 
        "wifipumpkin3", "ferret-sidejack", "hamster-sidejack"
    ],
    "Password Attacks & Enumeration": [
        "chntpw", "creddump7", "samdump2", "hashid", "hash-identifier", 
        "bopscrk", "cewl", "crunch", "maskgen", "policygen", "rsmangler", 
        "statsgen", "twofi", "wordlists", "crowbar", "hydra", "hydra-gtk", 
        "legba", "medusa", "ncrack", "patator", "sqldict", "thc-pptp-bruter", 
        "cmospwd", "crackle", "fcrackzip", "john", "johnny", "ophcrack", 
        "ophcrack-cli", "rcrack", "rcracki_mt", "sipcrack", "sucrack", 
        "truecrack", "gitxray", "trufflehog", "xspy", "svcrack", "enumiax", 
        "mfcuk", "mfoc", "mfterm", "mifare-classic-format", "nfc-list", 
        "nfc-mfclassic", "kerberoast", "krbrelayx", "responder"
    ],
    "Host Discovery & Infrastructure Protocols": [
        "apache-users", "smtp-user-enum", "enum4linux", "enum4linux-ng", 
        "nbtscan", "smbclient", "pspy", "pspy-binaries", "0trace.sh", 
        "ass", "cdp", "intrace", "netdiscover", "netmask", "sara", 
        "yersinia", "firewalk", "tcpreplay", "wafw00f", "impacket-mssqlclient", 
        "mdb-sql", "mysql", "oscanner", "sidguess", "sqlitebrowser", 
        "tnscmd10g", "mxcheck", "swaks", "cge.pl", "cisco-ocs", "cisco-torch", 
        "copy-router-config.pl", "merge-router-config.pl", "azurehound", 
        "bloodhound", "bloodhound-python", "bloodhound-ce-python", "ldeep", 
        "sharphound", "protos-sip", "rtpbreak", "rtpinsertsound", 
        "rtpmixsound", "siparmyknife", "sipp", "sippts", "sipsak", 
        "svcrash", "svmap", "svreport", "svwar", "voiphopper", "ohrwurm"
    ],
    "Data Transfer & Exfiltration": [
        "impacket-smbserver", "goshs", "raven", "cadaver", "minicom", 
        "dbd", "ncat", "netcat", "penelope", "powercat", "sbd", "socat", 
        "termineter", "chisel", "chisel-common-binaries", "dns2tcpc", 
        "dns2tcpd", "dnscat", "iodine-client-start", "ligolo-agent", 
        "ligolo-proxy", "ligolo-mp", "ligolo-mp-client", 
        "ligolo-ng-common-binaries", "miredo", "proxychains4", 
        "proxytunnel", "ptunnel", "pwnat", "sshuttle", "sslh", 
        "stunnel4", "udptunnel"
    ],
    "Denial of Service (DoS)": [
        "dhcpig", "goldeneye", "iaxflood", "inviteflood", "mdk3", 
        "rtpflood", "siege", "slowhttptest", "t50", "thc-ssl-dos"
    ],
    "Forensics & Incident Response": [
        "dc3dd", "dcfldd", "hexwalk", "missidentify", "readpst", 
        "reglookup", "regripper", "undbx", "vinetto", "ext3grep", 
        "ext4magic", "extundelete", "foremost", "magicrescue", "myrescue", 
        "pasco", "photorec", "readpe", "recoverdm", "recoverjpeg", 
        "rifiuti", "rifiuti2", "safecopy", "scalpel", "scrounge-ntfs", 
        "testdisk", "affcat", "dd_rescue", "ewfacquire", "guymager", 
        "pdfid", "pdf-parser", "autopsy", "blkcalc", "blkcat", "blkls", 
        "blkstat", "ffind", "fls", "fsstat", "grokevt-addlog", 
        "grokevt-builddb", "grokevt-findlogs", "grokevt-parselog", 
        "grokevt-ripdll", "hfind", "icat", "ifind", "ils", "img_cat", 
        "img_stat", "istat", "jcat", "jls", "mactime", "mmcat", "mmls", 
        "mmstat", "sigfind", "sorter", "srch_strings", "tsk_comparedir", 
        "tsk_gettimes", "tsk_loaddb", "tsk_recover", "binwalk", "binwalk3", 
        "bulk_extractor", "chkrootkit", "galleta", "hashdeep", "rkhunter", 
        "ssdeep", "unhide", "xplico-webui-start", "yara"
    ],
    "Reporting & Workspaces": [
        "cherrytree", "dradis-start", "faraday-start", "maltego", 
        "obsidian", "pipal", "recordmydesktop", "redeye-start", 
        "cutycapt", "eyewitness", "witnessme", "arsenal-ng", 
        "gemini-cli", "hexstrike_server", "kali-tweaks", "pwsh", 
        "root-terminal", "snapper-gui", "shell-gpt", "tailscale"
    ]
}

