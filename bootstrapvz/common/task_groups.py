from tasks import workspace
from tasks import packages
from tasks import host
from tasks import grub
from tasks import extlinux
from tasks import bootstrap
from tasks import volume
from tasks import loopback
from tasks import filesystem
from tasks import partitioning
from tasks import cleanup
from tasks import apt
from tasks import security
from tasks import locale
from tasks import network
from tasks import initd
from tasks import ssh
from tasks import kernel
from tasks import folder


def get_standard_groups(manifest):
    group = []
    group.extend(get_base_group(manifest))
    group.extend(volume_group)
    if manifest.volume['partitions']['type'] != 'none':
        group.extend(partitioning_group)
    if 'boot' in manifest.volume['partitions']:
        group.extend(boot_partition_group)
    group.extend(mounting_group)
    group.extend(kernel_group)
    group.extend(get_fs_specific_group(manifest))
    group.extend(get_network_group(manifest))
    group.extend(get_apt_group(manifest))
    group.extend(security_group)
    group.extend(get_locale_group(manifest))
    group.extend(get_bootloader_group(manifest))
    group.extend(cleanup_group)
    return group


def get_base_group(manifest):
    group = [workspace.CreateWorkspace,
             bootstrap.AddRequiredCommands,
             host.CheckExternalCommands,
             bootstrap.Bootstrap,
             workspace.DeleteWorkspace,
             ]
    if manifest.bootstrapper.get('tarball', False):
        group.append(bootstrap.MakeTarball)
    if manifest.bootstrapper.get('include_packages', False):
        group.append(bootstrap.IncludePackagesInBootstrap)
    if manifest.bootstrapper.get('exclude_packages', False):
        group.append(bootstrap.ExcludePackagesInBootstrap)
    return group


volume_group = [volume.Attach,
                volume.Detach,
                filesystem.AddRequiredCommands,
                filesystem.Format,
                filesystem.FStab,
                ]

partitioning_group = [partitioning.AddRequiredCommands,
                      partitioning.PartitionVolume,
                      partitioning.MapPartitions,
                      partitioning.UnmapPartitions,
                      ]

boot_partition_group = [filesystem.CreateBootMountDir,
                        filesystem.MountBoot,
                        ]

mounting_group = [filesystem.CreateMountDir,
                  filesystem.MountRoot,
                  filesystem.MountSpecials,
                  filesystem.CopyMountTable,
                  filesystem.RemoveMountTable,
                  filesystem.UnmountRoot,
                  filesystem.DeleteMountDir,
                  ]

kernel_group = [kernel.DetermineKernelVersion,
                kernel.UpdateInitramfs,
                ]

ssh_group = [ssh.AddOpenSSHPackage,
             ssh.DisableSSHPasswordAuthentication,
             ssh.DisableSSHDNSLookup,
             ssh.AddSSHKeyGeneration,
             initd.InstallInitScripts,
             ssh.ShredHostkeys,
             ]


def get_network_group(manifest):
    if manifest.bootstrapper.get('variant', None) == 'minbase':
        # minbase has no networking
        return []
    group = [network.ConfigureNetworkIF,
             network.RemoveDNSInfo]
    if manifest.system.get('hostname', False):
        group.append(network.SetHostname)
    else:
        group.append(network.RemoveHostname)
    return group


def get_apt_group(manifest):
    group = [apt.AddDefaultSources,
             apt.WriteSources,
             apt.DisableDaemonAutostart,
             apt.AptUpdate,
             apt.AptUpgrade,
             packages.InstallPackages,
             apt.PurgeUnusedPackages,
             apt.AptClean,
             apt.EnableDaemonAutostart,
             ]
    if 'sources' in manifest.packages:
        group.append(apt.AddManifestSources)
    if 'trusted-keys' in manifest.packages:
        group.append(apt.InstallTrustedKeys)
    if 'preferences' in manifest.packages:
        group.append(apt.AddManifestPreferences)
        group.append(apt.WritePreferences)
    if 'apt.conf.d' in manifest.packages:
        group.append(apt.WriteConfiguration)
    if 'install' in manifest.packages:
        group.append(packages.AddManifestPackages)
    if manifest.packages.get('install_standard', False):
        group.append(packages.AddTaskselStandardPackages)
    return group

security_group = [security.EnableShadowConfig]


def get_locale_group(manifest):
    from bootstrapvz.common.releases import jessie
    group = [
        locale.LocaleBootstrapPackage,
        locale.GenerateLocale,
        locale.SetTimezone,
    ]
    if manifest.release > jessie:
        group.append(locale.SetLocalTimeLink)
    else:
        group.append(locale.SetLocalTimeCopy)
    return group


def get_bootloader_group(manifest):
    from bootstrapvz.common.releases import jessie
    from bootstrapvz.common.releases import stretch
    group = []
    if manifest.system['bootloader'] == 'grub':
        group.extend([grub.AddGrubPackage,
                      grub.InitGrubConfig,
                      grub.SetGrubTerminalToConsole,
                      grub.SetGrubConsolOutputDeviceToSerial,
                      grub.RemoveGrubTimeout,
                      grub.DisableGrubRecovery,
                      grub.WriteGrubConfig])
        if manifest.release < jessie:
            group.append(grub.InstallGrub_1_99)
        else:
            group.append(grub.InstallGrub_2)
        if manifest.release >= stretch:
            group.append(grub.DisablePNIN)
    if manifest.system['bootloader'] == 'extlinux':
        group.append(extlinux.AddExtlinuxPackage)
        if manifest.release < jessie:
            group.extend([extlinux.ConfigureExtlinux,
                          extlinux.InstallExtlinux])
        else:
            group.extend([extlinux.ConfigureExtlinuxJessie,
                          extlinux.InstallExtlinuxJessie])
    return group


def get_fs_specific_group(manifest):
    partitions = manifest.volume['partitions']
    fs_specific_tasks = {'ext2': [filesystem.TuneVolumeFS],
                         'ext3': [filesystem.TuneVolumeFS],
                         'ext4': [filesystem.TuneVolumeFS],
                         'xfs':  [filesystem.AddXFSProgs],
                         }
    group = set()
    if 'boot' in partitions:
        group.update(fs_specific_tasks.get(partitions['boot']['filesystem'], []))
    if 'root' in partitions:
        group.update(fs_specific_tasks.get(partitions['root']['filesystem'], []))
    return list(group)


cleanup_group = [cleanup.ClearMOTD,
                 cleanup.CleanTMP,
                 ]


rollback_map = {workspace.CreateWorkspace:  workspace.DeleteWorkspace,
                loopback.Create:            volume.Delete,
                volume.Attach:              volume.Detach,
                partitioning.MapPartitions: partitioning.UnmapPartitions,
                filesystem.CreateMountDir:  filesystem.DeleteMountDir,
                filesystem.MountRoot:       filesystem.UnmountRoot,
                folder.Create:              folder.Delete,
                }


def get_standard_rollback_tasks(completed):
    rollback_tasks = set()
    for task in completed:
        if task not in rollback_map:
            continue
        counter = rollback_map[task]
        if task in completed and counter not in completed:
            rollback_tasks.add(counter)
    return rollback_tasks
