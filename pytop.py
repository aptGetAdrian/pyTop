import curses
import psutil
import time
import os
from datetime import datetime
import pynvml
import threading



'''

V primeru izpisa: "CPU Temp: N/A | GPU Temp & Fan: N/A" za temperaturo
porcesne enote ter temperaturo grafične enote.

Ker sem na linuxu in ker to pišem na prenosnem računalniku, 
imam težave s podatki s senzorjev, ki so zadolženi za poročanje
temperature procesne/grafične enote in hitrost ventilatorjev. 
Spodnja implementacija v funkcijah get_cpu_temperature(), 
get_gpu_temperature_and_fan() bi načeloma morala delovati.
Načeloma bi se jih dalo konfigurirati s pomojo ukazov, kot so
sudo sensors-detect, sudo modprobe k10temp itd...
ampak trenutno ne upam tvegati delovanje senzorjev, zato namesto 
dejanskega podatka dobim izpis "N/A" 




uporabniku prijaznejši vmesnik OK

interaktivno uporabo OK

ustavljanje procesov po imenu ukaza ali poti

izpis odprtih datotek/oprimkov procesa OK

pregled nad zasedenim pomnilnikom procesa OK

pregled nad odprtimi kanali komunikacije (Unix vtiči, TCP-UDP/IP vtiči, deljen pomnilnik, vrste za sporočila)

izpis procesov s podano delovno potjo

izpis procesov za podanega uporabnika


'''


threadLock = threading.Lock()
sortValue = 'cpu_percent'
running = True
filter = ""
filterMode = False
unixSockets = False
tcpSockets = False
udpSockets = False
monitor = True


def format_uptime():
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_struct = time.gmtime(uptime_seconds)
    return f"{uptime_struct.tm_yday - 1} days, {uptime_struct.tm_hour:02}:{uptime_struct.tm_min:02}"

def get_cpu_temperature():
    try:
        temps = psutil.sensors_temperatures()
        if "coretemp" in temps:
            return f"{temps['coretemp'][0].current:.1f}°C"
    except (AttributeError, KeyError):
        pass
    return "N/A"

def get_gpu_temperature_and_fan():
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
        pynvml.nvmlShutdown()
        return f"{gpu_temp}°C, Fan: {fan_speed}%"
    except pynvml.NVMLError:
        return "N/A"

def get_battery_status():
    battery = psutil.sensors_battery()
    if battery:
        percent = battery.percent
        charging = "Charging" if battery.power_plugged else "Discharging"
        return f"{percent:.1f}% ({charging})"
    else:
        return "N/A"

def get_top_header(stdscr):
    with threadLock:
        height, width = stdscr.getmaxyx()
    
    current_time = datetime.now().strftime("%H:%M:%S")
    uptime = format_uptime()
    users = len(psutil.users())
    load_avg = os.getloadavg()
    battery_status = get_battery_status()

    all_procs = list(psutil.process_iter(['status']))
    total_tasks = len(all_procs)
    running_tasks = sum(1 for p in all_procs if p.info['status'] == psutil.STATUS_RUNNING)
    sleeping_tasks = sum(1 for p in all_procs if p.info['status'] == psutil.STATUS_SLEEPING)
    stopped_tasks = sum(1 for p in all_procs if p.info['status'] == psutil.STATUS_STOPPED)
    zombie_tasks = sum(1 for p in all_procs if p.info['status'] == psutil.STATUS_ZOMBIE)

    cpu_times = psutil.cpu_times_percent(interval=1)
    cpu_summary = (f"{cpu_times.user:.1f} us, {cpu_times.system:.1f} sy, {cpu_times.nice:.1f} ni, "
                   f"{cpu_times.idle:.1f} id, {cpu_times.iowait:.1f} wa, {cpu_times.irq:.1f} hi, "
                   f"{cpu_times.softirq:.1f} si, {cpu_times.steal:.1f} st")

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    mem_info = (f"MiB Mem : {mem.total / 1024**2:.1f} total, {mem.available / 1024**2:.1f} free, "
                f"{mem.used / 1024**2:.1f} used, {mem.buffers / 1024**2:.1f} buff/cache")
    swap_info = (f"MiB Swap: {swap.total / 1024**2:.1f} total, {swap.free / 1024**2:.1f} free, "
                 f"{swap.used / 1024**2:.1f} used")

    cpu_temp = get_cpu_temperature()
    gpu_info = get_gpu_temperature_and_fan()

    header = [f"pyTop - {current_time} up {uptime}, {users} users, load average: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}",
              f"Tasks: {total_tasks} total, {running_tasks} running, {sleeping_tasks} sleeping, {stopped_tasks} stopped, {zombie_tasks} zombie",
              f"%CPU(s): {cpu_summary}",
              f"CPU Temp: {cpu_temp} | GPU Temp & Fan: {gpu_info} | Battery: {battery_status}",
              f"{mem_info}\n{swap_info}"]
    
    header2 = ""
    for x in header:
        if len(x) > width:
            x = x[4:width]

        header2 += x + "\n"

    return header2

def kill_process_by_name(name_or_path):
    with threadLock:
        for proc in psutil.process_iter(['name']):
            try:
                process_name = proc.info['name']
                process_path = proc.exe()

                if name_or_path.lower() in process_name.lower() or name_or_path.lower() in process_path.lower():
                    proc.terminate()  
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass



def footer(stdscr):
    global sortValue
    global running
    global filter, filterMode
    global unixSockets, tcpSockets, udpSockets, monitor
    with threadLock:
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.timeout(50)
        curses.init_color(8, 0, 0, 0)
        curses.init_pair(1, 8, curses.COLOR_MAGENTA)

    searchMode = False
    search_query = ""
    killMode = False

    
    footer = ["F1-sort cpu%", "F2-sort mem%", "F3-filter", "F4-kill", "F5-unix sockets", "F6-tcp sockets", "F7-udp sockets", "F8-processes", "F10-quit"]

    while running == True:
        try:
            with threadLock:
                height, width = stdscr.getmaxyx()
                for y in range(height - 1, height):  
                    stdscr.move(y, 0)
                    stdscr.clrtoeol()


            counter = 0

            with threadLock:
                if searchMode == True:
                    stdscr.addstr(height - 1, 0, f"Input: {search_query}".ljust(width-1), curses.color_pair(1))
                else:
                    for line in footer:
                        if counter + len(line) + 1 > width:
                            break 

                        stdscr.addstr(height - 1, counter, line, curses.A_REVERSE)
                        counter += len(line)
                        
                        if counter < width:
                            stdscr.addstr(height - 1, counter, " ")
                            counter += 1


                key = stdscr.getch()

                    
            if key == curses.KEY_F10:
                running = False

            if key == curses.KEY_F2:
                sortValue = 'memory_percent'

            if key == curses.KEY_F1:
                sortValue = 'cpu_percent'

            if key == curses.KEY_F3:
                with threadLock:
                    if filterMode == True:
                        filterMode = not filterMode
                        footer[2] = "F3 - filter"
                    else:
                        searchMode = not searchMode
                        search_query = ""
                        footer[2] = "F3 - cancel"
                
            
            if key == curses.KEY_F4:
                searchMode = not searchMode
                killMode = True
                search_query = ""

            if key == curses.KEY_F5:
                with threadLock:
                    stdscr.clear()
                    unixSockets = True
                    tcpSockets = False
                    udpSockets = False
                    monitor = False
            
            if key == curses.KEY_F6:
                with threadLock:
                    stdscr.clear()
                    unixSockets = False
                    tcpSockets = True
                    udpSockets = False
                    monitor = False

            if key == curses.KEY_F7:
                with threadLock:
                    stdscr.clear()
                    unixSockets = False
                    tcpSockets = False
                    udpSockets = True
                    monitor = False

            if key == curses.KEY_F8:
                
                with threadLock:
                    stdscr.clear()
                    unixSockets = False
                    tcpSockets = False
                    udpSockets = False
                    monitor = True


            if searchMode == True:
                if key == curses.KEY_BACKSPACE:
                    search_query = search_query[:-1]
                elif key == 10:  # Enter
                
                    if killMode == True:
                        kill_process_by_name(search_query)
                        killMode = False
                    else:
                        with threadLock:
                            filter = search_query
                            filterMode = True


                    searchMode = not searchMode  
                    search_query = ""
                elif 32 <= key <= 126:  # za crke pa stevilke
                    search_query += chr(key)
        
        except:
            continue



def menu(stdscr):
    global sortValue
    global filter, filterMode
    global unixSockets, tcpSockets, udpSockets, monitor
    caseNum = 0
    with threadLock:
        curses.curs_set(0)
        stdscr.nodelay(1)
        #stdscr.timeout(1000)
        curses.start_color()
        curses.init_color(8, 0, 0, 0)
        curses.init_pair(1, 8, curses.COLOR_MAGENTA)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)
        height, width = stdscr.getmaxyx()
    
    
    while running == True:

        with threadLock:
            if unixSockets == True:
                caseNum = 1
            elif tcpSockets == True:
                caseNum = 2
            elif udpSockets == True:
                caseNum = 3
            elif monitor == True:
                caseNum = 0



        match caseNum:
            
            case 0:
                try:
                        #stdscr.clear()
                        with threadLock:
                            num_cores = psutil.cpu_count()

                        start_line = 7 
                        max_processes = height - start_line - 1  

                        with threadLock:
                            for y in range(height, height-2):
                                stdscr.move(y, 0)
                                stdscr.clrtoeol()

                        header = "    PID   USER      PR  NI     RES    CPU%   MEM%   FD   NAME                   PATH"
                        processes = []
                        for proc in psutil.process_iter(['pid', 'username', 'cpu_percent', 
                                                'memory_percent', 'name', 'nice', 
                                                'memory_info', 'cpu_times']):
                            proc.cpu_percent()  

                        for proc in psutil.process_iter(['pid', 'username', 'cpu_percent', 
                                                        'memory_percent', 'name', 'nice', 
                                                        'memory_info', 'cpu_times']):
                            try:
                                pr_value = 20 + proc.info['nice']
                                processes.append({
                                    'pid': proc.info['pid'],  #pid procesa
                                    'pr': pr_value,  #prioriteta procesa
                                    'ni': proc.info['nice'],  #nice value
                                    'username': proc.info['username'],  #ime uporabnika
                                    'res': proc.info['memory_info'].rss // 1000**2,  #fizicana poraba glavnega pomnilnika
                                    'cpu_percent': proc.info['cpu_percent'] / num_cores,  #uporaba procesorja
                                    'memory_percent': proc.info['memory_percent'],  #zasedenost v pomnilniku
                                    'time': proc.info['cpu_times'].user + proc.info['cpu_times'].system,  #cpu time
                                    'name': proc.info['name'],  #ime procesa
                                    'fd_count': proc.num_fds(),  # file descriptors count
                                    'path': proc.exe()  # path 
                                })
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                        
                        
                        
                        
                        processes.sort(key=lambda x: x[sortValue], reverse=True)

                        top_header = get_top_header(stdscr)
                        with threadLock:
                            stdscr.addstr(0, 0, top_header)
                            stdscr.addstr(6, 0, header.ljust(width), curses.color_pair(1) | curses.A_BOLD)
                            counter = 0

                            if filterMode == True:
                                for i in range(start_line, height-1):
                                    stdscr.addstr(i, 0, ' ' * width)

                            for idx, proc in enumerate(processes[:max_processes]):
                                try:
                                    if filterMode:
                                        if proc['username'] == filter:

                                            if start_line + idx >= height - 1:
                                                break

                                            max_name_length = 18  
                                            truncated_name = proc['name'][:max_name_length] + ('...' if len(proc['name']) > max_name_length else '')

                                            line = f"{proc['pid']:7}   {proc['username']:8} {proc['pr']:3} {proc['ni']:3} {proc['res']:6}M  {proc['cpu_percent']:6.3f} {proc['memory_percent']:6.2f} {proc['fd_count']:4}   {truncated_name:20}   {proc['path']}"

                                            if len(line) > width:
                                                line = line[:width-3] + '...'

                                            if counter == 0:
                                                stdscr.addstr(start_line + counter, 0, line.ljust(width), curses.color_pair(2) | curses.A_ITALIC)
                                            else:
                                                if proc['username'] == "root":
                                                    stdscr.addstr(start_line + counter, 0, line.ljust(width), curses.A_BOLD | curses.A_ITALIC)
                                                else:
                                                    stdscr.addstr(start_line + counter, 0, line.ljust(width))

                                            counter += 1
                                        else:
                                            max_processes += 1
                                    else:
                                        if start_line + idx >= height - 1:
                                            break

                                       
                                        max_name_length = 18  
                                        truncated_name = proc['name'][:max_name_length] + ('...' if len(proc['name']) > max_name_length else '')

                                        line = f"{proc['pid']:7}   {proc['username']:8} {proc['pr']:3} {proc['ni']:3} {proc['res']:6}M  {proc['cpu_percent']:6.3f} {proc['memory_percent']:6.2f} {proc['fd_count']:4}   {truncated_name:20}   {proc['path']}"

                                        if len(line) > width:
                                            line = line[:width-3] + '...'

                                        if idx == 0:
                                            stdscr.addstr(start_line + idx, 0, line.ljust(width), curses.color_pair(2) | curses.A_ITALIC)
                                        else:
                                            if proc['username'] == "root":
                                                stdscr.addstr(start_line + idx, 0, line.ljust(width), curses.A_BOLD | curses.A_ITALIC)
                                            else:
                                                stdscr.addstr(start_line + idx, 0, line.ljust(width))
                                except (psutil.NoSuchProcess, KeyError):
                                    continue
                            
                            stdscr.getch()
                        

                except:
                    continue

            case 1:  
                try:
                    start_line = 1
                    max_connections = height - start_line - 1  

                    with threadLock:
                        for y in range(height, height-1):
                            stdscr.move(y, 0)
                            stdscr.clrtoeol()

                    header = f"    PID     FD   PATH"
                    stdscr.addstr(0, 0, header.ljust(width), curses.color_pair(1) | curses.A_BOLD)
                    unix_sockets = psutil.net_connections(kind='unix')
                    unix_info = [
                        {"fd": conn.fd, 
                         "path": conn.laddr if conn.laddr else "N/A", 
                         "raddr": conn.raddr if conn.raddr else "N/A",
                         "family": conn.family,
                         "pid": conn.pid,
                         
                         } for conn in unix_sockets if conn.laddr
                    ]
                    with threadLock:
                        for idx, proc in enumerate(unix_info[:max_connections]):
                            try:
                                    if start_line + idx >= height - 1:
                                        break
            
                                    line = f"{proc['pid']:7}    {proc['fd']:3}   {proc['path']:3}"

                                    if len(line) > width:
                                        line = line[:width-3] + '...'

                                    stdscr.addstr(start_line + idx, 0, line.ljust(width))
                            except (psutil.NoSuchProcess, KeyError):
                                continue
                            
                        stdscr.getch()

                except:
                    continue
            
            case 2:
                try:
                    start_line = 1
                    max_connections = height - start_line - 1  
                    with threadLock:
                        for y in range(height, height-1):
                            stdscr.move(y, 0)
                            stdscr.clrtoeol()

                    header = f"    PID    TYPE    LADDR                          RADDR                     STATUS"
                    stdscr.addstr(0, 0, header.ljust(width), curses.color_pair(1) | curses.A_BOLD)
                    tcp_sockets = psutil.net_connections(kind='tcp')
                    tcp_info = [
                        {"type": "TCP", 
                         "laddr": conn.laddr, 
                         "raddr": conn.raddr, 
                         "status": conn.status,
                         "pid": conn.pid,
                         } for conn in tcp_sockets
                    ]
                    with threadLock:
                        for idx, proc in enumerate(tcp_info[:max_connections]):
                            try:
                                    if start_line + idx >= height - 1:
                                        break
                                   
                                    line = (f"{proc['pid']:7}    {proc['type']:5}     "
                                            f"{':'.join(map(str, proc['laddr'])) if proc['laddr'] != 'N/A' else 'N/A':23}      "
                                            f"{':'.join(map(str, proc['raddr'])) if proc['raddr'] != 'N/A' else 'N/A':20}      "
                                            f"{proc['status']:10}")    

                                    if len(line) > width:
                                        line = line[:width-3] + '...'

                                    stdscr.addstr(start_line + idx, 0, line.ljust(width))
                            except (psutil.NoSuchProcess, KeyError):
                                continue
                            
                        stdscr.getch()

                except:
                    continue
            
            case 3:
                try:
                    start_line = 1
                    max_connections = height - start_line - 1  
                    with threadLock:
                        for y in range(height, height-1):
                            stdscr.move(y, 0)
                            stdscr.clrtoeol()

                    header = f"    PID    TYPE      LADDR                        RADDR"
                    stdscr.addstr(0, 0, header.ljust(width), curses.color_pair(1) | curses.A_BOLD)
                    udp_sockets = psutil.net_connections(kind='udp')
                    udp_info = [
                        {"type": "UDP", 
                         "laddr": conn.laddr, 
                         "raddr": conn.raddr, 
                         "pid": conn.pid,
                         } for conn in udp_sockets
                    ]
                    with threadLock:
                        for idx, proc in enumerate(udp_info[:max_connections]):
                            try:
                                    if start_line + idx >= height - 1:
                                        break                                                              
                                    line = (f"{proc['pid']:7}    {proc['type']:5}     "
                                            f"{':'.join(map(str, proc['laddr'])) if proc['laddr'] != 'N/A' else 'N/A':23}      "
                                            f"{':'.join(map(str, proc['raddr'])) if proc['raddr'] != 'N/A' else 'N/A':2}")    

                                    if len(line) > width:
                                        line = line[:width-3] + '...'

                                    stdscr.addstr(start_line + idx, 0, line.ljust(width))
                            except (psutil.NoSuchProcess, KeyError):
                                continue
                            
                        stdscr.getch()

                except:
                    continue


def main(stdscr):
    thread_footer = threading.Thread(target=footer, args=(stdscr,))
    thread_menu = threading.Thread(target=menu, args=(stdscr,))

    thread_footer.start()
    thread_menu.start()

    thread_footer.join()
    thread_menu.join()

if __name__ == "__main__":
    curses.wrapper(main)
